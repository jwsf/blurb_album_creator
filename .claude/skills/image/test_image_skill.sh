#!/usr/bin/env bash
set -euo pipefail

# Image skill test harness
# - Default mode: deterministic mock geocoding (fast, offline)
# - Live mode: real Nominatim calls (slow, network required)

USE_LIVE_GEOCODER=0
if [[ "${1:-}" == "--live" ]]; then
  USE_LIVE_GEOCODER=1
fi

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
GEOCODE_CALL_LOG="$(mktemp)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_FILE="$SCRIPT_DIR/SKILL.md"

TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT" "$GEOCODE_CALL_LOG"' EXIT

GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
RESET="\033[0m"

info() { echo "[INFO] $*"; }
skip() { printf "  %-52s ${YELLOW}SKIP${RESET}\n" "$*"; SKIP_COUNT=$((SKIP_COUNT + 1)); }

assert_eq() {
  local expected="$1"
  local actual="$2"
  local msg="$3"
  if [[ "$expected" == "$actual" ]]; then
    return 0
  fi
  echo "  expected: $expected"
  echo "  actual:   $actual"
  echo "  $msg"
  return 1
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local msg="$3"
  if grep -Fq -- "$needle" <<<"$haystack"; then
    return 0
  fi
  echo "  missing:  $needle"
  echo "  $msg"
  return 1
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  local msg="$3"
  if grep -Fq -- "$needle" <<<"$haystack"; then
    echo "  unexpected: $needle"
    echo "  $msg"
    return 1
  fi
  return 0
}

run_test() {
  local name="$1"
  local fn="$2"
  local detail
  if detail="$("$fn" 2>&1)"; then
    printf "  %-52s ${GREEN}PASS${RESET}\n" "$name"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    printf "  %-52s ${RED}FAIL${RESET}\n" "$name"
    [[ -n "$detail" ]] && echo "$detail" | sed 's/^/    /'
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

check_exiftool() {
  command -v exiftool >/dev/null 2>&1
}

check_curl() {
  command -v curl >/dev/null 2>&1
}

make_jpeg() {
  local out="$1"
  local ppm="${out%.jpg}.ppm"
  cat >"$ppm" <<'EOF'
P3
1 1
255
255 255 255
EOF
  sips -s format jpeg "$ppm" --out "$out" >/dev/null
  rm -f "$ppm"
}

make_png() {
  local out="$1"
  local ppm="${out%.png}.ppm"
  cat >"$ppm" <<'EOF'
P3
1 1
255
255 255 255
EOF
  sips -s format png "$ppm" --out "$out" >/dev/null
  rm -f "$ppm"
}

set_region_name() {
  local file="$1"
  local value="$2"
  exiftool -overwrite_original -RegionName="$value" "$file" >/dev/null
}

set_datetime_original() {
  local file="$1"
  local value="$2"
  exiftool -overwrite_original -DateTimeOriginal="$value" "$file" >/dev/null
}

set_gps() {
  local file="$1"
  local lat="$2"
  local lon="$3"
  local lat_ref="N"
  local lon_ref="E"
  local lat_abs="$lat"
  local lon_abs="$lon"

  if awk "BEGIN{exit !($lat < 0)}"; then
    lat_ref="S"
    lat_abs="${lat#-}"   # strip minus sign, preserving full decimal precision
  fi
  if awk "BEGIN{exit !($lon < 0)}"; then
    lon_ref="W"
    lon_abs="${lon#-}"   # strip minus sign, preserving full decimal precision
  fi

  exiftool -overwrite_original \
    -GPSLatitude="$lat_abs" \
    -GPSLatitudeRef="$lat_ref" \
    -GPSLongitude="$lon_abs" \
    -GPSLongitudeRef="$lon_ref" \
    "$file" >/dev/null
}

write_location() {
  local image="$1"
  local location="$2"
  exiftool -overwrite_original -IPTC:City="$location" "$image" >/dev/null
}

read_cached_location() {
  local image="$1"
  local location
  location="$(exiftool -IPTC:City -s3 "$image" 2>/dev/null || true)"
  if [[ -n "$location" ]]; then
    echo "$location"
    return 0
  fi
  return 1
}

has_cached_location() {
  local image="$1"
  read_cached_location "$image" >/dev/null 2>&1
}

clear_location_cache() {
  local image="$1"
  exiftool -overwrite_original -IPTC:City= "$image" >/dev/null
}

pick_place_from_json() {
  python3 -c '
import json, sys
obj = json.load(sys.stdin)
addr = obj.get("address", {})
place = (addr.get("village") or
         addr.get("town") or
         addr.get("city") or
         addr.get("suburb") or
         addr.get("county") or
         addr.get("state") or
         addr.get("country") or
         "Unknown")
print(place)
'
}

get_place_name_mock() {
  local lat="$1"
  local lon="$2"
  echo "call" >> "$GEOCODE_CALL_LOG"  # file-based counter survives subshells

  # Use glob patterns to absorb minor floating-point variation in exiftool output
  case "$lat,$lon" in
    37.7749*,-122.4194*) echo "San Francisco" ;;
    37.8044*,-122.2712*) echo "Oakland" ;;
    40.748*,-73.985*) echo "Manhattan" ;;
    *) echo "Unknown" ;;
  esac
}

get_place_name_live() {
  local lat="$1"
  local lon="$2"
  GEOCODE_CALLS=$((GEOCODE_CALLS + 1))
  sleep 1
  local response
  response="$(curl -s "https://nominatim.openstreetmap.org/reverse?format=json&lat=$lat&lon=$lon&zoom=18&addressdetails=1" \
    -H "User-Agent: BlurbAlbumCreator/1.0")"
  echo "$response" | pick_place_from_json
}

get_place_name() {
  local lat="$1"
  local lon="$2"
  if [[ "$USE_LIVE_GEOCODER" -eq 1 ]]; then
    get_place_name_live "$lat" "$lon"
  else
    get_place_name_mock "$lat" "$lon"
  fi
}

infer_directory_location() {
  local dir="$1"
  local temp_locations
  temp_locations="$(mktemp)"

  while IFS= read -r image; do
    local lat lon place
    lat="$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null || true)"
    lon="$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null || true)"
    if [[ -n "$lat" && -n "$lon" ]]; then
      place="$(get_place_name "$lat" "$lon")"
      echo "$place" >>"$temp_locations"
    fi
  done < <(find "$dir" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" -o -iname "*.webp" \) | sort)

  if [[ -s "$temp_locations" ]]; then
    sort "$temp_locations" | uniq -c | sort -rn | head -1 | awk '{$1=""; sub(/^ /, ""); print}'
    rm -f "$temp_locations"
    return 0
  fi

  rm -f "$temp_locations"
  echo "Unknown"
}

get_location() {
  local image="$1"
  local cached lat lon place

  if cached="$(read_cached_location "$image" 2>/dev/null)"; then
    echo "$cached"
    return 0
  fi

  lat="$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null || true)"
  lon="$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null || true)"
  if [[ -n "$lat" && -n "$lon" ]]; then
    place="$(get_place_name "$lat" "$lon")"
    if [[ "$place" != "Unknown" ]]; then
      write_location "$image" "$place"
    fi
    echo "$place"
    return 0
  fi

  place="$(infer_directory_location "$(dirname "$image")")"
  if [[ "$place" != "Unknown" ]]; then
    write_location "$image" "$place"
  fi
  echo "$place"
}

generate_caption() {
  local image="$1"
  local people_raw people place caption count

  people_raw="$(exiftool -RegionName -s3 "$image" 2>/dev/null || true)"
  people="$(echo "$people_raw" | tr ',' '\n' | tr ';' '\n' | sed 's/^ *//' | sed 's/ *$//' | sed '/^$/d')"
  place="$(get_location "$image")"

  caption=""
  if [[ -n "$people" ]]; then
    count="$(echo "$people" | wc -l | tr -d ' ')"
    if [[ "$count" == "1" ]]; then
      caption="$people"
    elif [[ "$count" == "2" ]]; then
      local n1 n2
      n1="$(echo "$people" | sed -n '1p')"
      n2="$(echo "$people" | sed -n '2p')"
      caption="$n1 and $n2"
    else
      local all_but_last last
      all_but_last="$(echo "$people" | sed '$d' | paste -sd ', ' -)"  # sed '$d' = drop last line (macOS-compatible)
      last="$(echo "$people" | tail -1)"
      caption="$all_but_last, and $last"
    fi
  fi

  if [[ "$place" != "Unknown" ]]; then
    if [[ -n "$caption" ]]; then
      caption="$caption in $place"
    else
      caption="$place"
    fi
  fi

  echo "$caption"
}

get_coordinates_safe() {
  local image="$1"
  if [[ ! -f "$image" ]]; then
    return 1
  fi

  local lat lon
  lat="$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null || true)"
  lon="$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null || true)"
  if [[ -z "$lat" || -z "$lon" ]]; then
    return 1
  fi

  if awk "BEGIN{exit !($lat < -90 || $lat > 90)}"; then
    return 1
  fi
  if awk "BEGIN{exit !($lon < -180 || $lon > 180)}"; then
    return 1
  fi

  echo "$lat,$lon"
}

analyze_image() {
  local image="$1"
  local people place date_taken
  people="$(exiftool -RegionName -s3 "$image" 2>/dev/null || true)"
  place="$(get_location "$image")"
  date_taken="$(exiftool -DateTimeOriginal -s3 "$image" 2>/dev/null || true)"

  echo "File: $image"
  echo "People: ${people:-none}"
  echo "Location: $place"
  echo "Date taken: ${date_taken:-unknown}"
}

find_person() {
  local person_name="$1"
  local search_dir="$2"
  while IFS= read -r image; do
    local people
    people="$(exiftool -RegionName -s3 "$image" 2>/dev/null || true)"
    if echo "$people" | grep -qi "$person_name"; then
      echo "$image"
    fi
  done < <(find "$search_dir" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" -o -iname "*.webp" \) | sort)
}

setup_fixtures() {
  mkdir -p "$TEST_ROOT/gps-city-a" "$TEST_ROOT/gps-mixed" "$TEST_ROOT/no-gps" "$TEST_ROOT/mixed" "$TEST_ROOT/unknown-gps" "$TEST_ROOT/nested/day1" "$TEST_ROOT/nested/day2" "$TEST_ROOT/people"

  make_jpeg "$TEST_ROOT/gps-city-a/sf_1.jpg"
  make_jpeg "$TEST_ROOT/gps-city-a/sf_2.jpg"
  make_jpeg "$TEST_ROOT/gps-city-a/sf_3.jpg"
  make_jpeg "$TEST_ROOT/gps-mixed/sf_4.jpg"
  make_jpeg "$TEST_ROOT/gps-mixed/oak_1.jpg"
  make_jpeg "$TEST_ROOT/gps-mixed/oak_2.jpg"
  make_jpeg "$TEST_ROOT/no-gps/no_1.jpg"
  make_jpeg "$TEST_ROOT/no-gps/no_2.jpg"
  make_jpeg "$TEST_ROOT/mixed/m_1.jpg"
  make_jpeg "$TEST_ROOT/mixed/m_2.jpg"
  make_jpeg "$TEST_ROOT/unknown-gps/u_1.jpg"
  make_jpeg "$TEST_ROOT/nested/day1/n1.jpg"
  make_jpeg "$TEST_ROOT/nested/day2/n2.jpg"
  make_png  "$TEST_ROOT/people/p_1.png"
  make_jpeg "$TEST_ROOT/people/p_2.jpg"

  set_gps "$TEST_ROOT/gps-city-a/sf_1.jpg" 37.7749 -122.4194
  set_gps "$TEST_ROOT/gps-city-a/sf_2.jpg" 37.7749 -122.4194
  set_gps "$TEST_ROOT/gps-city-a/sf_3.jpg" 37.7749 -122.4194

  set_gps "$TEST_ROOT/gps-mixed/sf_4.jpg" 37.7749 -122.4194
  set_gps "$TEST_ROOT/gps-mixed/oak_1.jpg" 37.8044 -122.2712
  set_gps "$TEST_ROOT/gps-mixed/oak_2.jpg" 37.8044 -122.2712

  set_gps "$TEST_ROOT/mixed/m_1.jpg" 40.748817 -73.985428
  set_gps "$TEST_ROOT/unknown-gps/u_1.jpg" 0.12345 0.54321

  set_gps "$TEST_ROOT/nested/day1/n1.jpg" 37.7749 -122.4194
  set_gps "$TEST_ROOT/nested/day2/n2.jpg" 37.7749 -122.4194

  set_region_name "$TEST_ROOT/people/p_1.png" "John Doe"
  set_region_name "$TEST_ROOT/people/p_2.jpg" "John Doe, Jane Smith; Bob Jones"

  set_datetime_original "$TEST_ROOT/people/p_2.jpg" "2025:10:14 13:30:00"
}

# ---------- Tests ----------

test_prereq_exiftool_present() {
  check_exiftool
}

test_prereq_curl_present() {
  check_curl
}

test_prereq_exiftool_missing_path() {
  ( PATH="/nonexistent"; check_exiftool ) && return 1 || return 0
}

test_location_cache_write_read_clear() {
  local img="$TEST_ROOT/no-gps/no_1.jpg"
  write_location "$img" "Testville"
  local got
  got="$(read_cached_location "$img")"
  assert_eq "Testville" "$got" "Cache read should match write" || return 1
  has_cached_location "$img" || return 1
  clear_location_cache "$img"
  has_cached_location "$img" && return 1 || return 0
}

test_place_priority_parser() {
  local json place
  json='{"address":{"country":"USA","state":"California","county":"San Francisco County","city":"San Francisco","town":"TownX","village":"VillageY"}}'
  place="$(echo "$json" | pick_place_from_json)"
  assert_eq "VillageY" "$place" "Village should win in priority order"
}

test_get_location_cache_first() {
  local img="$TEST_ROOT/no-gps/no_2.jpg"
  > "$GEOCODE_CALL_LOG"  # reset counter
  write_location "$img" "CachedPlace"
  local loc calls
  loc="$(get_location "$img")"
  calls="$(wc -l < "$GEOCODE_CALL_LOG" | tr -d ' ')"
  assert_eq "CachedPlace" "$loc" "Cache-first lookup should return IPTC city" || return 1
  assert_eq "0" "$calls" "Cache hit should avoid geocoding"
}

test_get_location_geocode_and_cache() {
  local img="$TEST_ROOT/gps-city-a/sf_1.jpg"
  > "$GEOCODE_CALL_LOG"  # reset counter
  clear_location_cache "$img"
  local loc cached calls
  loc="$(get_location "$img")"
  cached="$(read_cached_location "$img" || true)"
  calls="$(wc -l < "$GEOCODE_CALL_LOG" | tr -d ' ')"
  assert_eq "San Francisco" "$loc" "GPS geocode should resolve to San Francisco" || return 1
  assert_eq "San Francisco" "$cached" "Location should be cached to IPTC:City" || return 1
  [[ "$calls" -ge 1 ]] || { echo "Expected at least 1 geocode call, got $calls"; return 1; }
}

test_infer_directory_location_majority() {
  local loc
  GEOCODE_CALLS=0
  loc="$(infer_directory_location "$TEST_ROOT/gps-mixed")"
  assert_eq "Oakland" "$loc" "Majority location should be selected"
}

test_infer_directory_location_unknown() {
  local loc
  loc="$(infer_directory_location "$TEST_ROOT/no-gps")"
  assert_eq "Unknown" "$loc" "No GPS in directory should return Unknown"
}

test_get_location_directory_inference() {
  local src="$TEST_ROOT/mixed/m_2.jpg"
  local gps_peer="$TEST_ROOT/mixed/m_1.jpg"
  > "$GEOCODE_CALL_LOG"  # reset counter
  clear_location_cache "$src"
  clear_location_cache "$gps_peer"
  local loc calls
  loc="$(get_location "$src")"
  calls="$(wc -l < "$GEOCODE_CALL_LOG" | tr -d ' ')"
  assert_eq "Manhattan" "$loc" "Non-GPS image should infer from folder peers" || return 1
  [[ "$calls" -ge 1 ]] || { echo "Expected at least 1 geocode call, got $calls"; return 1; }
}

test_get_location_unknown_not_cached() {
  local img="$TEST_ROOT/unknown-gps/u_1.jpg"
  clear_location_cache "$img"
  local loc
  loc="$(get_location "$img")"
  assert_eq "Unknown" "$loc" "Unmapped GPS should return Unknown" || return 1
  if has_cached_location "$img"; then
    echo "Unknown must not be cached in IPTC:City"
    return 1
  fi
}

test_generate_caption_single_person() {
  local img="$TEST_ROOT/people/p_1.png"
  write_location "$img" "Waikiki"
  local caption
  caption="$(generate_caption "$img")"
  assert_eq "John Doe in Waikiki" "$caption" "Single person caption format"
}

test_generate_caption_three_people() {
  local img="$TEST_ROOT/people/p_2.jpg"
  write_location "$img" "Honolulu"
  local caption
  caption="$(generate_caption "$img")"
  assert_contains "$caption" "John Doe" "Caption should include first name" || return 1
  assert_contains "$caption" "Jane Smith" "Caption should include second name" || return 1
  assert_contains "$caption" "Bob Jones" "Caption should include third name" || return 1
  assert_contains "$caption" "in Honolulu" "Caption should include location"
}

test_generate_caption_location_only() {
  local img="$TEST_ROOT/no-gps/no_1.jpg"
  clear_location_cache "$img"
  write_location "$img" "OnlyPlace"
  local caption
  caption="$(generate_caption "$img")"
  assert_eq "OnlyPlace" "$caption" "No people should produce location-only caption"
}

test_generate_caption_dynamic_updates() {
  local img="$TEST_ROOT/people/p_1.png"
  write_location "$img" "DynamicTown"
  local c1 c2
  c1="$(generate_caption "$img")"
  set_region_name "$img" "John Doe, Jane Smith"
  c2="$(generate_caption "$img")"
  [[ "$c1" != "$c2" ]] || return 1
  assert_contains "$c2" "Jane Smith" "Caption should reflect updated people tags"
}

test_get_coordinates_safe_valid() {
  local img="$TEST_ROOT/gps-city-a/sf_2.jpg"
  local coords
  coords="$(get_coordinates_safe "$img")"
  assert_contains "$coords" "," "Safe coordinate extraction should return lat,lon"
}

test_get_coordinates_safe_invalid_file() {
  get_coordinates_safe "$TEST_ROOT/does-not-exist.jpg" && return 1 || return 0
}

test_analyze_image_output() {
  local out
  out="$(analyze_image "$TEST_ROOT/people/p_2.jpg")"
  assert_contains "$out" "File:" "Analyze output should include file" || return 1
  assert_contains "$out" "People:" "Analyze output should include people" || return 1
  assert_contains "$out" "Location:" "Analyze output should include location"
}

test_find_person_positive_negative() {
  local pos neg
  pos="$(find_person "John Doe" "$TEST_ROOT/people")"
  neg="$(find_person "NotARealName" "$TEST_ROOT/people")"
  [[ -n "$pos" ]] || return 1
  [[ -z "$neg" ]]
}

test_csv_export_columns() {
  local csv="$TEST_ROOT/out.csv"
  exiftool -FileName -RegionName -GPSPosition -DateTimeOriginal -n -csv -r "$TEST_ROOT" >"$csv"
  local header
  header="$(head -1 "$csv")"
  assert_contains "$header" "SourceFile" "CSV should include SourceFile" || return 1
  assert_contains "$header" "FileName" "CSV should include FileName" || return 1
  assert_contains "$header" "RegionName" "CSV should include RegionName"
}

test_recursive_directory_processing() {
  local count
  count="$(find "$TEST_ROOT/nested" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | wc -l | tr -d ' ')"
  assert_eq "2" "$count" "Nested directory images should be discoverable recursively"
}

test_skill_doc_mentions_core_behaviors() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "IPTC:City" "Skill doc should mention IPTC:City cache" || return 1
  assert_contains "$body" "Nominatim" "Skill doc should mention geocoding provider" || return 1
  assert_contains "$body" "Captions are NOT cached" "Skill doc should state dynamic captions"
}

test_skill_doc_no_return_trap_for_temp_cleanup() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_not_contains "$body" "trap 'rm -f \"\$temp_locations\" \"\$coords_file\"' RETURN" "RETURN trap-based cleanup should not be used in infer_directory_location"
}

test_skill_doc_high_precision_coordinate_keys() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "%.5f,%.5f" "Coordinate cache keys should use 5-decimal precision"
}

test_skill_doc_optimized_cache_lookup_strategy() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "awk -F'\\t' 'NR==FNR" "regenerate_all_locations should use keyed join strategy" || return 1
  assert_not_contains "$body" "grep \"^\$key=\" \"\$coords_cache\"" "O(n^2) grep-per-image cache lookup should not be present"
}

test_skill_doc_curl_resilience_flags() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "--connect-timeout 5" "curl should define connect timeout" || return 1
  assert_contains "$body" "--max-time 20" "curl should define max request time" || return 1
  assert_contains "$body" "--retry 2" "curl should retry transient failures"
}

test_skill_doc_analyze_directory_top_level_only() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "Analyze All Images in Directory (Top-Level Only)" "analyze_directory section should explicitly state top-level-only behavior" || return 1
  assert_contains "$body" "does not scan subdirectories" "analyze_directory description should clarify non-recursive behavior"
}

test_skill_doc_unknown_never_cached_wording() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "only when the place is not `Unknown`" "Skill doc should state Unknown values are not cached"
}

test_skill_doc_no_double_sleep_in_batch_geocode() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "get_place_name()" "Skill doc should define get_place_name" || return 1
  assert_not_contains "$body" "sleep 1  # Respect rate limit" "batch_geocode should not add an extra sleep beyond get_place_name"
}

test_skill_doc_no_bc_dependency_in_coordinate_validation() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_not_contains "$body" "| bc -l" "Coordinate validation should not require bc"
  assert_contains "$body" "if awk \"BEGIN{exit !(\$lat < -90 || \$lat > 90)}\"; then" "Latitude validation should use awk" || return 1
  assert_contains "$body" "if awk \"BEGIN{exit !(\$lon < -180 || \$lon > 180)}\"; then" "Longitude validation should use awk"
}

test_skill_doc_inference_ignores_unknown() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "if [ \"\$place\" != \"Unknown\" ]; then" "infer_directory_location should ignore Unknown geocode results in majority calculation"
}

test_skill_doc_analyze_directory_no_first_pass_inference() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_not_contains "$body" "# First pass: infer directory location" "analyze_directory should not do redundant first-pass inference"
  assert_not_contains "$body" "dir_location=$(infer_directory_location \"\$dir\")" "analyze_directory should rely on per-image cache-first get_location"
}

test_skill_doc_reverse_geocode_sample_is_hardened() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "response=\$(curl -fsS --connect-timeout 5 --max-time 20 --retry 2 --retry-delay 1" "reverse geocode sample should include hardened curl flags" || return 1
  assert_contains "$body" "except Exception:" "reverse geocode sample should handle JSON parse failures"
}

test_skill_doc_read_cached_location_has_local_var() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" "read_cached_location()" "read_cached_location helper should exist" || return 1
  assert_contains "$body" "  local location" "read_cached_location should localize location variable"
}

test_skill_doc_has_cached_location_has_local_var() {
  local fn_block
  fn_block="$(awk '
    /has_cached_location\(\) \{/ {in_fn=1}
    in_fn {print}
    in_fn && /^}/ {exit}
  ' "$SKILL_FILE")"
  assert_contains "$fn_block" "has_cached_location()" "has_cached_location helper should exist" || return 1
  assert_contains "$fn_block" "  local location" "has_cached_location should localize location variable" || return 1
  assert_contains "$fn_block" 'location=$(exiftool -IPTC:City -s3 "$image" 2>/dev/null)' "has_cached_location should read IPTC City"
}

test_skill_doc_traps_are_restored_after_temp_cleanup() {
  local body
  body="$(cat "$SKILL_FILE")"
  assert_contains "$body" 'old_int_trap=$(trap -p INT || true)' "temp cleanup snippets should capture existing INT trap" || return 1
  assert_contains "$body" 'old_term_trap=$(trap -p TERM || true)' "temp cleanup snippets should capture existing TERM trap" || return 1
  assert_contains "$body" 'if [ -n "$old_int_trap" ]; then' "temp cleanup snippets should restore or clear INT trap" || return 1
  assert_contains "$body" 'if [ -n "$old_term_trap" ]; then' "temp cleanup snippets should restore or clear TERM trap"
}

test_skill_doc_analyze_directory_localizes_loop_vars() {
  local fn_block
  fn_block="$(awk '
    /analyze_directory\(\) \{/ {in_fn=1}
    in_fn {print}
    in_fn && /^}/ {exit}
  ' "$SKILL_FILE")"
  assert_contains "$fn_block" '  local image people lat lon place date_taken' "analyze_directory should localize per-image working variables"
}

test_skill_doc_analyze_directory_reduces_metadata_overhead() {
  local fn_block
  fn_block="$(awk '
    /analyze_directory\(\) \{/ {in_fn=1}
    in_fn {print}
    in_fn && /^}/ {exit}
  ' "$SKILL_FILE")"
  assert_contains "$fn_block" 'mapfile -t meta < <(exiftool -RegionName -GPSLatitude# -GPSLongitude# -DateTimeOriginal -s3 "$image" 2>/dev/null)' "analyze_directory should use one metadata read per image" || return 1
  assert_not_contains "$fn_block" 'people=$(exiftool -RegionName -s3 "$image" 2>/dev/null)' "analyze_directory should avoid per-field people reads" || return 1
  assert_not_contains "$fn_block" 'lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)' "analyze_directory should avoid separate latitude reads" || return 1
  assert_not_contains "$fn_block" 'lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)' "analyze_directory should avoid separate longitude reads" || return 1
  assert_not_contains "$fn_block" 'date_taken=$(exiftool -DateTimeOriginal -s3 "$image" 2>/dev/null)' "analyze_directory should avoid separate date reads" || return 1
  assert_contains "$fn_block" 'if [ -z "$inferred_dir_location" ]; then' "analyze_directory should cache inferred directory location for no-GPS images"
}

main() {
  info "Using test root: $TEST_ROOT"
  if [[ "$USE_LIVE_GEOCODER" -eq 1 ]]; then
    info "Geocoder mode: LIVE (Nominatim)"
  else
    info "Geocoder mode: MOCK (deterministic/offline)"
  fi

  # Hard prerequisite checks — abort before any test runs
  if ! check_exiftool; then
    echo "ERROR: exiftool is required but not installed."
    echo "  macOS: brew install exiftool"
    echo "  Linux: apt-get install libimage-exiftool-perl"
    exit 1
  fi
  if ! command -v sips >/dev/null 2>&1; then
    echo "ERROR: sips is required but not available (macOS only)."
    exit 1
  fi
  if ! check_curl; then
    echo "ERROR: curl is required but not installed."
    exit 1
  fi

  setup_fixtures

  run_test "Prereq exiftool present" test_prereq_exiftool_present
  run_test "Prereq curl present" test_prereq_curl_present
  run_test "Prereq exiftool missing path" test_prereq_exiftool_missing_path

  run_test "Location cache write/read/clear" test_location_cache_write_read_clear
  run_test "Place priority parser" test_place_priority_parser
  run_test "Get location cache-first" test_get_location_cache_first
  run_test "Get location geocode and cache" test_get_location_geocode_and_cache
  run_test "Infer directory location majority" test_infer_directory_location_majority
  run_test "Infer directory location unknown" test_infer_directory_location_unknown
  run_test "Get location directory inference" test_get_location_directory_inference
  run_test "Get location unknown not cached" test_get_location_unknown_not_cached

  run_test "Generate caption single person" test_generate_caption_single_person
  run_test "Generate caption three people" test_generate_caption_three_people
  run_test "Generate caption location only" test_generate_caption_location_only
  run_test "Generate caption dynamic updates" test_generate_caption_dynamic_updates

  run_test "Safe coordinates valid" test_get_coordinates_safe_valid
  run_test "Safe coordinates invalid file" test_get_coordinates_safe_invalid_file
  run_test "Analyze image output" test_analyze_image_output
  run_test "Find person positive/negative" test_find_person_positive_negative
  run_test "CSV export columns" test_csv_export_columns
  run_test "Recursive directory processing" test_recursive_directory_processing
  run_test "Skill doc mentions core behaviors" test_skill_doc_mentions_core_behaviors
  run_test "Skill doc avoids RETURN trap cleanup" test_skill_doc_no_return_trap_for_temp_cleanup
  run_test "Skill doc uses high-precision coord keys" test_skill_doc_high_precision_coordinate_keys
  run_test "Skill doc uses optimized cache lookup" test_skill_doc_optimized_cache_lookup_strategy
  run_test "Skill doc has curl resilience flags" test_skill_doc_curl_resilience_flags
  run_test "Skill doc marks top-level-only analysis" test_skill_doc_analyze_directory_top_level_only
  run_test "Skill doc says Unknown is not cached" test_skill_doc_unknown_never_cached_wording
  run_test "Skill doc avoids double batch sleep" test_skill_doc_no_double_sleep_in_batch_geocode
  run_test "Skill doc avoids bc dependency" test_skill_doc_no_bc_dependency_in_coordinate_validation
  run_test "Skill doc inference ignores Unknown" test_skill_doc_inference_ignores_unknown
  run_test "Skill doc removes first-pass inference" test_skill_doc_analyze_directory_no_first_pass_inference
  run_test "Skill doc reverse sample is hardened" test_skill_doc_reverse_geocode_sample_is_hardened
  run_test "Skill doc localizes cached-location var" test_skill_doc_read_cached_location_has_local_var
  run_test "Skill doc localizes has-cached var" test_skill_doc_has_cached_location_has_local_var
  run_test "Skill doc restores prior signal traps" test_skill_doc_traps_are_restored_after_temp_cleanup
  run_test "Skill doc localizes analyze vars" test_skill_doc_analyze_directory_localizes_loop_vars
  run_test "Skill doc optimizes analyze metadata" test_skill_doc_analyze_directory_reduces_metadata_overhead

  echo
  echo "Test summary: pass=$PASS_COUNT fail=$FAIL_COUNT skip=$SKIP_COUNT"

  if [[ "$FAIL_COUNT" -ne 0 ]]; then
    exit 1
  fi
}

main "$@"
