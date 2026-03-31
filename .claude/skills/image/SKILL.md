---
name: image
description: Extract and update metadata from image files including people names and locations
---

# Image Metadata Handler Skill

This skill handles extracting and processing metadata from image files, including:
- People names from XMP face regions
- Geographic location data
- Reverse geocoding (coordinates to place names)
- Location inference for images without GPS data

## Required Tools

### exiftool
The primary tool for reading and writing image metadata.

**Installation:**
- macOS: `brew install exiftool`
- Linux: `apt-get install libimage-exiftool-perl` or `yum install perl-Image-ExifTool`
- Windows: Download from https://exiftool.org/

**Check if installed:**
```bash
which exiftool || echo "exiftool not found - please install"
```

### curl
Used for reverse geocoding API calls (typically pre-installed on most systems).

## Supported Image Formats

- JPEG/JPG (.jpg, .jpeg)
- PNG (.png)
- HEIC (.heic) - Apple's format
- TIFF (.tiff, .tif)
- RAW formats (.cr2, .nef, .arw, .dng, etc.)
- GIF (.gif)
- WebP (.webp)

## Single-Level Caching Strategy

This skill uses image-level caching only for complete portability:

### Location Cache (Image-Level Only)
Reverse geocoded location names are stored **inside each image file** in IPTC location fields:
- **Storage**: `IPTC:City` (primary location name - smallest granularity)
- **Benefit**: Location data travels with the image file (fully portable)
- **Avoids**: Repeated geocoding API calls for the same image
- **Standard field**: Compatible with photo management software (Lightroom, Photos, etc.)
- **When to clear/regenerate**: If you want different location granularity or names changed
- **Priority**: Checked BEFORE GPS geocoding
- **No system cache**: All location data stored in image files only

### Dynamic Caption Generation Workflow

**Captions are NOT cached** - they are generated dynamically from:
- People names (from XMP face regions)
- Cached location (from IPTC:City)

When generating captions:
1. **Extract people names** from XMP face regions
2. **Get location name** (cache-first):
   - **Check IPTC:City** in image metadata (location cache)
   - If found → use cached location
   - If not found:
     - Extract GPS coordinates or infer from directory
     - Call Nominatim API to get place name
     - **Write location to IPTC:City** in image metadata
3. **Build caption dynamically** from people + location
4. **Return caption** (NOT cached - generated fresh each time)

This single-level strategy keeps all data portable with image files, while allowing captions to always reflect current people names and locations.

## People Name Extraction

### XMP Face Region Standards

People names are typically stored in XMP face region data using these standards:
- **Microsoft Photo**: `XMP-mwg-rs:RegionName`
- **Picasa**: `XMP-mwg-rs:RegionName`
- **Adobe Lightroom**: `XMP-lr:HierarchicalSubject` or `XMP-mwg-rs:RegionName`
- **Apple Photos**: `XMP-MP:RegionName`

### Extract People Names from Single Image

```bash
# Method 1: Extract all region names (most common)
exiftool -XMP-mwg-rs:RegionName -s3 "image.jpg"

# Method 2: Extract Microsoft Photo Gallery person tags
exiftool -RegionName -s3 "image.jpg"

# Method 3: Extract all XMP person-related fields
exiftool -a -G1 -s -XMP:*Person* -XMP:*Region* "image.jpg"

# Method 4: Get all region info (detailed)
exiftool -struct -XMP-mwg-rs:RegionInfo "image.jpg"
```

### Extract People Names from Multiple Images

```bash
# Get people names from all images in directory
exiftool -RegionName -s3 -r /path/to/images/

# Get people names with filenames
exiftool -FileName -RegionName -csv -r /path/to/images/ > people_names.csv

# Count occurrences of each person across all images
exiftool -RegionName -s3 -r /path/to/images/ | sort | uniq -c | sort -rn
```

### Parse Multiple People from One Image

Some images have multiple people. The output format varies:
```bash
# Example output: "John Doe, Jane Smith, Bob Jones"
exiftool -RegionName -s3 "family_photo.jpg"

# Parse into individual names (comma or semicolon separated)
exiftool -RegionName -s3 "family_photo.jpg" | tr ',' '\n' | tr ';' '\n' | sed 's/^ *//' | sed 's/ *$//'
```

## Dynamic Caption Generation

**IMPORTANT**: Captions are NOT cached - they are generated dynamically from people names and cached location data.

### Caption Components

Captions are built from two sources:
- **People names**: Extracted from XMP face regions
- **Location**: From IPTC:City cache (or geocoded if not cached)

This allows captions to always reflect current metadata without needing cache invalidation.

## Location Data Extraction

### GPS Coordinates

GPS data is stored in EXIF format:
- **GPSLatitude** - Latitude coordinate
- **GPSLongitude** - Longitude coordinate
- **GPSLatitudeRef** - North (N) or South (S)
- **GPSLongitudeRef** - East (E) or West (W)

### Extract GPS Coordinates from Single Image

```bash
# Get GPS coordinates in decimal format (easiest to use)
exiftool -GPSPosition -n "image.jpg"
# Output: GPS Position: 40.748817 -73.985428

# Get individual components
exiftool -GPSLatitude -GPSLongitude -GPSLatitudeRef -GPSLongitudeRef "image.jpg"

# Get GPS as simple lat/lon values
lat=$(exiftool -GPSLatitude -n -s3 "image.jpg")
lon=$(exiftool -GPSLongitude -n -s3 "image.jpg")
echo "Latitude: $lat, Longitude: $lon"
```

### Extract GPS from Multiple Images

```bash
# Get GPS coordinates from all images in directory
exiftool -FileName -GPSPosition -n -csv -r /path/to/images/ > gps_data.csv

# Find images WITH GPS data
exiftool -if '$GPSLatitude' -FileName -GPSPosition -n -r /path/to/images/

# Find images WITHOUT GPS data
exiftool -if 'not $GPSLatitude' -FileName -r /path/to/images/
```

## Location Caching in Image Metadata

**IMPORTANT**: Location names (from reverse geocoding) are cached inside image files using IPTC location fields for portability.

### Location Storage Fields

Use IPTC Core location fields (compatible with all photo management software):
- **IPTC:City** - Primary location name (e.g., "San Francisco")
- **IPTC:Province-State** - State/province (optional, for more detail)
- **IPTC:Country-PrimaryLocationName** - Country (optional, for more detail)

### Write Location to Image

```bash
# Write location name to image metadata
write_location() {
  local image="$1"
  local location="$2"

  exiftool -overwrite_original \
    -IPTC:City="$location" \
    "$image"

  echo "Cached location in image: $location"
}

# Usage
write_location "photo.jpg" "San Francisco"
```

### Read Cached Location from Image

```bash
# Read cached location from image
read_cached_location() {
  local image="$1"

  location=$(exiftool -IPTC:City -s3 "$image" 2>/dev/null)

  if [ -n "$location" ]; then
    echo "$location"
    return 0
  fi

  # No cached location found
  return 1
}

# Usage
if cached=$(read_cached_location "photo.jpg"); then
  echo "Cached location: $cached"
else
  echo "No cached location found"
fi
```

### Check if Location is Cached

```bash
# Check if image has cached location
has_cached_location() {
  local image="$1"

  location=$(exiftool -IPTC:City -s3 "$image" 2>/dev/null)

  if [ -n "$location" ]; then
    return 0
  else
    return 1
  fi
}

# Usage
if has_cached_location "photo.jpg"; then
  echo "Location is cached"
else
  echo "Location not cached"
fi
```

### Clear Location Cache

Clear cached locations from one or more images:

```bash
# Clear cached location from single image
clear_location_cache() {
  local image="$1"

  exiftool -overwrite_original \
    -IPTC:City= \
    "$image"

  echo "Location cache cleared: $image"
}

# Clear cached locations from all images in directory
clear_all_location_caches() {
  local dir="$1"

  echo "Clearing location caches from all images in: $dir"

  count=0
  while IFS= read -r image; do
    if has_cached_location "$image"; then
      clear_location_cache "$image"
      ((count++))
    fi
  done < <(find "$dir" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \))

  echo "Cleared $count cached locations"
}

# Usage
clear_location_cache "photo.jpg"
clear_all_location_caches "inputs/vacation"
```

### Regenerate Location Cache

Force regeneration of cached locations (re-geocode):

```bash
# Regenerate location for single image (clear and geocode again)
regenerate_location() {
  local image="$1"

  echo "Regenerating location for: $(basename "$image")"

  # Clear existing cache
  clear_location_cache "$image"

  # Get GPS coordinates
  lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)
  lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)

  if [ -n "$lat" ] && [ -n "$lon" ]; then
    # Geocode to get place name
    place=$(get_place_name "$lat" "$lon")

    # Cache the new location
    write_location "$image" "$place"

    echo "New location: $place"
  else
    echo "No GPS data found"
  fi
}

# Regenerate all locations in directory
regenerate_all_locations() {
  local dir="$1"

  echo "Regenerating all locations in: $dir"
  echo ""

  # First pass: clear all location caches
  clear_all_location_caches "$dir"

  # Second pass: regenerate locations
  count=0
  while IFS= read -r image; do
    lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)
    lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)

    if [ -n "$lat" ] && [ -n "$lon" ]; then
      place=$(get_place_name "$lat" "$lon")
      write_location "$image" "$place"
      echo "  $(basename "$image"): $place"
      ((count++))
    fi
  done < <(find "$dir" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \))

  echo ""
  echo "Regenerated $count locations"
}

# Usage
regenerate_location "photo.jpg"
regenerate_all_locations "inputs/vacation"
```

### Cache-First Location Retrieval

Always check IPTC location cache before geocoding:

```bash
# Get location with cache-first approach
get_location() {
  local image="$1"

  # First: Check IPTC location cache
  if cached=$(read_cached_location "$image" 2>/dev/null); then
    echo "$cached"
    return 0
  fi

  # Second: Get from GPS + geocoding
  lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)
  lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)

  if [ -n "$lat" ] && [ -n "$lon" ]; then
    # Geocode to get place name
    place=$(get_place_name "$lat" "$lon")

    # Cache in image metadata for future use
    write_location "$image" "$place"

    echo "$place"
    return 0
  fi

  # Third: Try to infer from directory
  place=$(infer_directory_location "$(dirname "$image")")

  if [ "$place" != "Unknown" ]; then
    # Cache inferred location
    write_location "$image" "$place"
  fi

  echo "$place"
}

# Usage
location=$(get_location "photo.jpg")
echo "Location: $location"
```

## Reverse Geocoding (Coordinates to Place Names)

### Using Nominatim (OpenStreetMap)

**Free service with usage limits:**
- Maximum 1 request per second
- Must include User-Agent header
- No API key required

**API Endpoint:**
```
https://nominatim.openstreetmap.org/reverse?format=json&lat=LAT&lon=LON&zoom=18&addressdetails=1
```

**Zoom levels for detail:**
- 18: Building level (most detailed)
- 16: Street level
- 14: Town/village level
- 12: City level
- 10: County/state level
- 8: Country level

### Reverse Geocode Single Location

```bash
# Get place name from coordinates
lat="40.748817"
lon="-73.985428"

response=$(curl -s "https://nominatim.openstreetmap.org/reverse?format=json&lat=$lat&lon=$lon&zoom=18&addressdetails=1" \
  -H "User-Agent: BlurbAlbumCreator/1.0")

# Extract address components
echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
addr = data.get('address', {})
print('Village:', addr.get('village', ''))
print('Town:', addr.get('town', ''))
print('City:', addr.get('city', ''))
print('County:', addr.get('county', ''))
print('State:', addr.get('state', ''))
print('Country:', addr.get('country', ''))
"
```

### Preferred Place Name Priority

When converting coordinates to a place name, use this priority order:
1. **Village** - `address.village`
2. **Town** - `address.town`
3. **City** - `address.city`
4. **Suburb** - `address.suburb` (if no village/town/city)
5. **County** - `address.county`
6. **State** - `address.state`
7. **Country** - `address.country`

```bash
# Extract preferred place name with priority
get_place_name() {
  local lat="$1"
  local lon="$2"

  # Respect rate limit (1 request per second)
  sleep 1

  response=$(curl -s "https://nominatim.openstreetmap.org/reverse?format=json&lat=$lat&lon=$lon&zoom=18&addressdetails=1" \
    -H "User-Agent: BlurbAlbumCreator/1.0")

  # Extract place name with priority
  place=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    addr = data.get('address', {})
    # Priority: village > town > city > suburb > county > state > country
    place = (addr.get('village') or
             addr.get('town') or
             addr.get('city') or
             addr.get('suburb') or
             addr.get('county') or
             addr.get('state') or
             addr.get('country') or
             'Unknown')
    print(place)
except:
    print('Unknown')
")

  echo "$place"
}

# Usage
place=$(get_place_name "40.748817" "-73.985428")
echo "Location: $place"
```

### Full Location String

Sometimes you may want the full location hierarchy:

```bash
# Get full location string (Village, County, State, Country)
get_full_location() {
  local lat="$1"
  local lon="$2"

  sleep 1

  response=$(curl -s "https://nominatim.openstreetmap.org/reverse?format=json&lat=$lat&lon=$lon&zoom=18&addressdetails=1" \
    -H "User-Agent: BlurbAlbumCreator/1.0")

  location=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    addr = data.get('address', {})
    parts = []

    # Add most specific place
    place = addr.get('village') or addr.get('town') or addr.get('city') or addr.get('suburb')
    if place:
        parts.append(place)

    # Add county/state
    region = addr.get('county') or addr.get('state')
    if region and (not parts or region != parts[-1]):
        parts.append(region)

    # Add country
    country = addr.get('country')
    if country:
        parts.append(country)

    print(', '.join(parts) if parts else 'Unknown')
except:
    print('Unknown')
")

  echo "$location"
}

# Usage
location=$(get_full_location "40.748817" "-73.985428")
echo "Full location: $location"
```

## Directory-Level Location Inference

For images without GPS data, infer location from other images in the same directory.

### Strategy

1. Scan all images in the directory
2. Extract GPS coordinates from images that have them
3. Convert coordinates to place names
4. Find the most common place name
5. Assign that place name to images without GPS data

### Implementation

```bash
# Infer location for images in a directory
infer_directory_location() {
  local dir="$1"

  echo "Analyzing images in: $dir"

  # Create temp file for locations
  temp_locations=$(mktemp)

  # Extract GPS from all images in directory
  while IFS= read -r image; do
    # Get GPS coordinates
    lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)
    lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)

    if [ -n "$lat" ] && [ -n "$lon" ]; then
      # Get place name
      place=$(get_place_name "$lat" "$lon")
      echo "$place" >> "$temp_locations"
      echo "  $(basename "$image"): $place (from GPS)"
    fi
  done < <(find "$dir" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \) | sort)

  # Find most common location
  if [ -s "$temp_locations" ]; then
    common_location=$(sort "$temp_locations" | uniq -c | sort -rn | head -1 | awk '{$1=""; print substr($0,2)}')

    rm "$temp_locations"
    echo "$common_location"
  else
    rm "$temp_locations"
    echo "Unknown"
  fi
}

# Usage
inferred_location=$(infer_directory_location "/path/to/images")
```

## Complete Image Analysis

### Analyze Single Image

Get all relevant metadata from one image:

```bash
analyze_image() {
  local image="$1"

  echo "=== Image Analysis: $(basename "$image") ==="
  echo ""

  # File info
  echo "File: $image"
  filesize=$(ls -lh "$image" | awk '{print $5}')
  echo "Size: $filesize"
  echo ""

  # People names
  echo "People:"
  people=$(exiftool -RegionName -s3 "$image" 2>/dev/null)
  if [ -n "$people" ]; then
    echo "$people" | tr ',' '\n' | tr ';' '\n' | sed 's/^ *//' | sed 's/ *$//' | while read -r person; do
      echo "  - $person"
    done
  else
    echo "  (none found)"
  fi
  echo ""

  # Location
  echo "Location:"
  lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)
  lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)

  if [ -n "$lat" ] && [ -n "$lon" ]; then
    echo "  GPS: $lat, $lon"
    place=$(get_place_name "$lat" "$lon")
    echo "  Place: $place"
  else
    echo "  (no GPS data)"
    # Try to infer from directory
    dir=$(dirname "$image")
    inferred=$(infer_directory_location "$dir")
    echo "  Inferred: $inferred"
  fi
  echo ""

  # Date taken
  date_taken=$(exiftool -DateTimeOriginal -s3 "$image" 2>/dev/null)
  if [ -n "$date_taken" ]; then
    echo "Date taken: $date_taken"
  fi

  echo ""
}

# Usage
analyze_image "photo.jpg"
```

### Analyze All Images in Directory

Generate a report for all images:

```bash
analyze_directory() {
  local dir="$1"
  local output_file="$2"

  echo "Analyzing all images in: $dir"
  echo "Output file: $output_file"
  echo ""

  # Header
  {
    echo "Image Analysis Report"
    echo "Generated: $(date)"
    echo "Directory: $dir"
    echo ""
    echo "=========================="
    echo ""
  } > "$output_file"

  # First pass: infer directory location
  echo "Determining directory location..."
  dir_location=$(infer_directory_location "$dir")
  echo "Directory location: $dir_location"
  echo ""

  # Second pass: analyze each image
  echo "Analyzing individual images..."
  while IFS= read -r image; do
    echo "Processing: $(basename "$image")"

    {
      echo "--- $(basename "$image") ---"
      echo ""

      # People
      people=$(exiftool -RegionName -s3 "$image" 2>/dev/null)
      if [ -n "$people" ]; then
        echo "People: $people"
      else
        echo "People: (none)"
      fi

      # Location
      lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)
      lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)

      if [ -n "$lat" ] && [ -n "$lon" ]; then
        place=$(get_place_name "$lat" "$lon")
        echo "Location: $place (GPS: $lat, $lon)"
      else
        echo "Location: $dir_location (inferred from directory)"
      fi

      # Date
      date_taken=$(exiftool -DateTimeOriginal -s3 "$image" 2>/dev/null)
      if [ -n "$date_taken" ]; then
        echo "Date: $date_taken"
      fi

      echo ""
    } >> "$output_file"
  done < <(find "$dir" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \) | sort)

  echo ""
  echo "Analysis complete. Report saved to: $output_file"
}

# Usage
analyze_directory "inputs/vacation_photos" "vacation_report.txt"
```

## Batch Operations

### Export All Metadata to CSV

```bash
# Export people and location data for all images
exiftool -FileName -RegionName -GPSPosition -DateTimeOriginal -n -csv -r /path/to/images > metadata.csv
```

### Add Location to Images Without GPS

If you know the location for images without GPS, you can add it:

```bash
# Add GPS coordinates to image
exiftool -GPSLatitude=40.748817 -GPSLongitude=-73.985428 -GPSLatitudeRef=N -GPSLongitudeRef=W "image.jpg"

# Add GPS to all images in directory
exiftool -GPSLatitude=40.748817 -GPSLongitude=-73.985428 -GPSLatitudeRef=N -GPSLongitudeRef=W /path/to/images/
```

## Caching Considerations

### Location Caching (Image-Level Only)

**IMPORTANT**: This skill does NOT use a system-level cache. All location data is cached within image files using IPTC:City.

**Benefits:**
- Fully portable - cache travels with images
- No system files to manage
- Works across different machines
- Compatible with photo management software

**How it works:**
- When geocoding is needed, call Nominatim API directly
- Immediately cache result in image file (IPTC:City)
- Subsequent caption generation uses cached IPTC:City
- No system cache files needed

## Rate Limiting

**Important:** Nominatim has a strict usage policy:
- Maximum 1 request per second
- Always include a User-Agent header
- Consider setting up your own Nominatim instance for heavy usage

```bash
# Rate-limited batch geocoding
batch_geocode() {
  local input_file="$1"  # CSV with lat,lon columns

  while IFS=',' read -r lat lon; do
    place=$(get_place_name "$lat" "$lon")
    echo "$lat,$lon,$place"
    sleep 1  # Respect rate limit
  done < "$input_file"
}
```

## Error Handling

```bash
# Robust exiftool check
check_exiftool() {
  if ! command -v exiftool &> /dev/null; then
    echo "ERROR: exiftool is not installed"
    echo ""
    echo "Install with:"
    echo "  macOS: brew install exiftool"
    echo "  Linux: apt-get install libimage-exiftool-perl"
    echo ""
    return 1
  fi
  return 0
}

# Robust coordinate extraction with validation
get_coordinates_safe() {
  local image="$1"

  if [ ! -f "$image" ]; then
    echo "ERROR: File not found: $image" >&2
    return 1
  fi

  lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)
  lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)

  # Validate coordinates
  if [ -z "$lat" ] || [ -z "$lon" ]; then
    return 1
  fi

  # Check if coordinates are valid ranges
  if (( $(echo "$lat < -90 || $lat > 90" | bc -l) )); then
    echo "ERROR: Invalid latitude: $lat" >&2
    return 1
  fi

  if (( $(echo "$lon < -180 || $lon > 180" | bc -l) )); then
    echo "ERROR: Invalid longitude: $lon" >&2
    return 1
  fi

  echo "$lat,$lon"
  return 0
}
```

## Use Cases

### Use Case 1: Generate Album Page Captions

Extract people and location for photo album captions. Captions are generated dynamically using cached location data.

```bash
# Generate caption dynamically from people names and cached location
generate_caption() {
  local image="$1"

  # Get people names from XMP face regions
  people=$(exiftool -RegionName -s3 "$image" 2>/dev/null | tr ',' '\n' | tr ';' '\n' | sed 's/^ *//' | sed 's/ *$//' | sed '/^$/d')

  # Get location using cache-first approach
  # First: Check IPTC location cache
  place=$(exiftool -IPTC:City -s3 "$image" 2>/dev/null)

  if [ -z "$place" ]; then
    # Second: Get from GPS coordinates
    lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)
    lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)

    if [ -n "$lat" ] && [ -n "$lon" ]; then
      # Geocode to get place name
      place=$(get_place_name "$lat" "$lon")

      # Cache location in image metadata for future use
      exiftool -overwrite_original -IPTC:City="$place" "$image" 2>/dev/null
    else
      # Third: Infer from directory
      place=$(infer_directory_location "$(dirname "$image")")

      # Cache inferred location in image metadata
      if [ "$place" != "Unknown" ]; then
        exiftool -overwrite_original -IPTC:City="$place" "$image" 2>/dev/null
      fi
    fi
  fi

  # Build caption dynamically
  caption=""
  if [ -n "$people" ]; then
    # Convert to "Name1 and Name2" or "Name1, Name2, and Name3"
    count=$(echo "$people" | wc -l)
    if [ "$count" -eq 1 ]; then
      caption="$people"
    elif [ "$count" -eq 2 ]; then
      name1=$(echo "$people" | sed -n '1p')
      name2=$(echo "$people" | sed -n '2p')
      caption="$name1 and $name2"
    else
      names=$(echo "$people" | sed '$d' | paste -sd ',' -)  # sed '$d' drops last line (macOS-compatible)
      last_name=$(echo "$people" | tail -1)
      caption="$names, and $last_name"
    fi
  fi

  # Add location
  if [ "$place" != "Unknown" ]; then
    if [ -n "$caption" ]; then
      caption="$caption in $place"
    else
      caption="$place"
    fi
  fi

  # Return dynamically generated caption (NOT cached)
  echo "$caption"
}

# Usage examples
caption=$(generate_caption "vacation/beach.jpg")
echo "Caption: $caption"
# Output: "John Doe and Jane Smith in Waikiki Beach"

# Generate again - will use cached location but rebuild caption
caption=$(generate_caption "vacation/beach.jpg")
echo "Caption: $caption"
# Output: Always current based on people names and cached location
```

### Use Case 2: Organize Photos by Location

Sort photos into directories by location:

```bash
organize_by_location() {
  local source_dir="$1"
  local dest_dir="$2"

  mkdir -p "$dest_dir"

  while IFS= read -r image; do
    lat=$(exiftool -GPSLatitude -n -s3 "$image" 2>/dev/null)
    lon=$(exiftool -GPSLongitude -n -s3 "$image" 2>/dev/null)

    if [ -n "$lat" ] && [ -n "$lon" ]; then
      place=$(get_place_name "$lat" "$lon")
    else
      place="Unknown"
    fi

    # Create location directory
    place_dir="$dest_dir/$place"
    mkdir -p "$place_dir"

    # Copy image
    cp "$image" "$place_dir/"
    echo "Copied $(basename "$image") to $place/"
  done < <(find "$source_dir" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" \))
}

# Usage
organize_by_location "inputs" "outputs/by_location"
```

### Use Case 3: Find All Photos of a Person

Search for all photos containing a specific person:

```bash
find_person() {
  local person_name="$1"
  local search_dir="$2"

  echo "Searching for photos of: $person_name"
  echo ""

  while IFS= read -r image; do
    people=$(exiftool -RegionName -s3 "$image" 2>/dev/null)
    if echo "$people" | grep -qi "$person_name"; then
      echo "Found: $image"
    fi
  done < <(find "$search_dir" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" \))
}

# Usage
find_person "John Doe" "inputs"
```

## Best Practices

1. **Always check if exiftool is installed** before running operations
2. **Use cache-first location lookup** - Read IPTC:City before GPS geocoding
3. **Respect Nominatim policy** - 1 request/second with a User-Agent header
4. **Validate coordinates** - Check lat/lon ranges before geocoding
5. **Handle missing data gracefully** - Not all images have people names or GPS
6. **Use directory-level inference** - Infer from nearby images when GPS is missing
7. **Preserve original files** - Use `-overwrite_original` carefully with exiftool
8. **Regenerate location cache when needed** - Rebuild IPTC:City if granularity or source data changes

## Workflow

When invoked with `/image`:

1. **Check prerequisites:**
   - Verify exiftool is installed
   - Verify curl is available

2. **Determine user intent:**
   - Analyze single image
   - Analyze directory of images
   - Extract people names
   - Extract locations
   - Generate captions (dynamic; location is cache-first)
   - Organize by location
   - Find specific person
   - **Cache management:**
     - Clear location cache (if user says "clear location cache", "clear locations", etc.)
     - Regenerate location cache (if user says "regenerate locations", "recreate locations", etc.)

3. **Execute operation:**
   - **For caption generation:** follow the Dynamic Caption Generation Workflow above
   - **For location cache clearing:**
     - Remove IPTC:City from image metadata
   - **For location cache regeneration:**
     - Clear existing location caches (IPTC:City)
     - Re-geocode all images with GPS data
     - Write new locations to IPTC:City

4. **Format output:**
   - Present data in readable format
   - Indicate whether location was cached or newly geocoded
   - Save to file if requested
   - Show summary statistics

5. **Report results:**
   - Number of images processed
   - Number with cached locations
   - Number with newly geocoded locations
   - Number with people names
   - Number with GPS data
   - Number with inferred locations

## Notes

- **Single-level caching**: store location only in IPTC:City (no system cache)
- **Captions are dynamic**: regenerate from current people tags plus cache-first location
- **Location lookup order**: IPTC:City -> GPS geocoding -> directory inference
- **Place priority**: village > town > city > suburb > county > state > country
- **Location regeneration** is needed when:
  - You want different location granularity (city vs village)
  - Place names have changed
  - GPS coordinates were updated
- **Cache commands** recognized:
  - "clear location cache" / "clear locations" - Remove cached locations from IPTC:City
  - "regenerate locations" / "recreate locations" - Clear and re-geocode all locations
- **XMP face regions** vary by software (Microsoft Photo, Picasa, Lightroom, Apple Photos)
- **GPS coordinates** are in EXIF format (degrees, minutes, seconds or decimal)
- **Nominatim** is free but has rate limits (1 req/sec with User-Agent required)
- **Privacy consideration**: Be aware that location and people data may be sensitive
