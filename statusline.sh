#!/usr/bin/env bash
# Claude Code status line script
# Usage: receives JSON on stdin, outputs formatted status line

input=$(cat)

# Extract fields from JSON input
dir=$(echo "$input" | jq -r '.workspace.current_dir // empty')
model=$(echo "$input" | jq -r '.model.display_name // empty')
remaining=$(echo "$input" | jq -r '.context_window.remaining_percentage // empty')

# Build output
out=""

# Add current directory (show just the last two path components for brevity)
if [ -n "$dir" ]; then
  # Shorter: show basename if path is long
  parent=$(dirname "$dir" 2>/dev/null || echo "")
  base=$(basename "$dir" 2>/dev/null || echo "$dir")
  if [ -n "$parent" ] && [ "$parent" != "." ]; then
    parent_base=$(basename "$parent" 2>/dev/null || echo "")
    if [ -n "$parent_base" ] && [ "$parent_base" != "/" ]; then
      out=".../$parent_base/$base"
    else
      out="$base"
    fi
  else
    out="$dir"
  fi
fi

# Add model name
if [ -n "$model" ]; then
  out="$out | $model"
fi

# Add remaining context percentage
if [ -n "$remaining" ]; then
  # Round to integer
  remaining_int=$(printf '%.0f' "$remaining" 2>/dev/null || echo "$remaining")
  out="$out | Context: ${remaining_int}% remaining"
fi

echo "$out"
