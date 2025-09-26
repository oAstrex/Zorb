#!/bin/bash

# --- Configuration ---
SOURCE_DIR="mounts/torbox"
LINK_DIR="mounts/media_library"
DRY_RUN="false" # ALWAYS run with "true" first to check its work!
# ---------------------

# --- Subdirectory Configuration ---
MOVIES_DIR="$LINK_DIR/Movies"
SHOWS_DIR="$LINK_DIR/TV Shows"

mkdir -p "$MOVIES_DIR" "$SHOWS_DIR"

echo "Starting the organization process (V3)..."
echo "---------------------------------"

for source_path in "$SOURCE_DIR"/*; do
    if [ ! -d "$source_path" ]; then
        continue
    fi

    filename=$(basename "$source_path")
    clean_name=""
    destination_folder=""

    # --- NEW: Special handling for one-off files ---
    # If we find this specific hash, we handle it manually and skip the rest of the logic
    if [[ "$filename" == "c39ac0a8f26fdddc407012b300b38d7847a8ef67" ]]; then
        clean_name="The Rookie S03"
        destination_folder="$SHOWS_DIR"
    else
        # --- IMPROVED: Logic to sort into Movies or TV Shows ---
        # This is now much better at finding season markers
        if [[ "$filename" =~ (\.S[0-9]+|[Ss]eason\.[0-9]+|\ S[0-9]+|\[S[0-9]+) ]]; then
            destination_folder="$SHOWS_DIR"
        else
            destination_folder="$MOVIES_DIR"
        fi

        # --- MORE RUTHLESS CLEANING ---
        # This pipeline is much more effective now.
        temp_name=$(echo "$filename" | sed -E \
            -e 's/[\._]/ /g' \
            -e 's/\[[^]]*\]//g' \
            -e 's/\([^)]*\)//g' \
        )
        
        # Standardize season format to SXX and normalize quality tags
        temp_name=$(echo "$temp_name" | sed -E \
            -e 's/[Ss]eason ([0-9]{2,})/S\1/g' \
            -e 's/[Ss]eason ([0-9])/S0\1/g' \
            -e 's/\bS([0-9])\b/S0\1/g' \
            -e 's/2160p/4k/ig' \
            -e 's/HDR10Plus/HDR10+/ig' \
        )

        # This is the "terminator." It finds the last important tag and deletes everything after it.
        # It keeps Title, Year, Quality, and HDR info, then chops the rest.
        terminators="4k|1080p|720p|DV|HDR10\+|HDR|S[0-9]{2}"
        clean_name=$(echo "$temp_name" | sed -E "s/(.*($terminators)).*/\1/")
    fi
    
    # Final cleanup: remove any leftover junk words and fix spacing
    junk_words="WEBRip|WEB-DL|BluRay|AMZN|NF|IMAX|REPACK|COMPLETE|TRUEFRENCH|MULTi|VF2|ENG|LATINO|HINDI|CUSTOM|AD|Hybrid|x265|HEVC|H264|AV1|AAC|DDP5 1|DDP5|8CH|6CH|Opus|Atmos"
    clean_name=$(echo "$clean_name" | sed -E "s/\b($junk_words)\b//ig")
    clean_name=$(echo "$clean_name" | sed -E 's/ +/ /g; s/^[ ]*//; s/[ ]*$//')


    # --- The Action ---
    if [ -n "$clean_name" ]; then
        folder_type=$(basename "$destination_folder")
        echo "ORIGINAL: $filename"
        echo "CLEANED:  $clean_name"
        
        if [ "$DRY_RUN" = "false" ]; then
            mkalias "$source_path" "$destination_folder/$clean_name"
            echo "--> Created symlink in '$folder_type'."
        else
            echo "--> (Dry Run) Would create symlink in '$folder_type'."
        fi
        echo ""
    fi
done

echo "All done!"