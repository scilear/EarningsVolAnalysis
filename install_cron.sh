#!/bin/bash
# Install crontab for options data collection (APPENDS to existing crontab)

set -e

PROJECT_DIR="/home/fabien/Documents/EarningsVolAnalysis"
CRONTAB_FILE="${PROJECT_DIR}/crontab.txt"

echo "=========================================="
echo "NVDA Options Data Collection - Cron Setup"
echo "=========================================="
echo ""

# Check if crontab file exists
if [ ! -f "${CRONTAB_FILE}" ]; then
    echo "ERROR: Crontab file not found: ${CRONTAB_FILE}"
    exit 1
fi

echo "Current crontab:"
echo "----------------"
crontab -l 2>/dev/null || echo "(empty - no crontab set)"
echo ""

echo "New entries to APPEND:"
echo "----------------------"
echo ""
cat "${CRONTAB_FILE}"
echo ""

read -p "Append these entries to crontab? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Backup existing crontab
    crontab -l > "${PROJECT_DIR}/logs/crontab_backup_$(date +%Y%m%d_%H%M%S).txt" 2>/dev/null || true
    
    # Get existing crontab and append new entries
    existing_crontab=$(crontab -l 2>/dev/null || echo "")
    
    # Create new crontab with separator comment
    new_crontab="${existing_crontab}

# ============================================
# NVDA Options Data Collection (Added: $(date))
# ============================================

$(cat "${CRONTAB_FILE}")"
    
    # Install combined crontab
    echo "${new_crontab}" | crontab -
    
    echo ""
    echo "✓ Crontab updated successfully!"
    echo ""
    echo "Schedule Summary:"
    echo "-----------------"
    echo "Frequency: Every 15 minutes"
    echo "Minutes: 01, 16, 31, 46 (offset to avoid startup delays)"
    echo "Hours: 8:31 AM - 5:01 PM ET (Mon-Fri)"
    echo "  - 8:31, 8:46: Pre-market (1h before open)"
    echo "  - 9:01-16:46: Market hours (9:30 AM - 4:00 PM)"
    echo "  - 17:01: Post-market (1h after close)"
    echo "Total runs/day: ~30"
    echo ""
    echo "Commands:"
    echo "  View:   crontab -l"
    echo "  Edit:   crontab -e"
    echo "  Remove: crontab -r"
    echo ""
    
    # Show next few scheduled runs
    echo "Next scheduled runs (if today is a weekday):"
    current_hour=$(date +%H)
    current_min=$(date +%M)
    current_dow=$(date +%u)
    
    if [ "$current_dow" -ge 1 ] && [ "$current_dow" -le 5 ]; then
        minute_slots=(1 16 31 46)
        shown=0
        
        for hour in 8 9 10 11 12 13 14 15 16 17; do
            if [ "$hour" -lt "$current_hour" ]; then
                continue
            fi
            
            for min in "${minute_slots[@]}"; do
                if [ "$hour" -eq "$current_hour" ] && [ "$min" -le "$current_min" ]; then
                    continue
                fi
                
                # Check if within valid range
                if [ "$hour" -lt 8 ]; then
                    continue
                fi
                if [ "$hour" -eq 8 ] && [ "$min" -lt 31 ]; then
                    continue
                fi
                if [ "$hour" -gt 17 ]; then
                    continue
                fi
                if [ "$hour" -eq 17 ] && [ "$min" -gt 1 ]; then
                    continue
                fi
                
                printf "  %02d:%02d ET\n" $hour $min
                ((shown++))
                
                if [ $shown -ge 8 ]; then
                    break 2
                fi
            done
        done
        
        if [ $shown -eq 0 ]; then
            echo "  (No more runs today - after 17:01 ET)"
        fi
    else
        echo "  (Today is weekend - runs start Monday)"
    fi
    
    echo ""
    echo "Log files:"
    echo "  ${PROJECT_DIR}/logs/nvda_01min.log"
    echo ""
    echo "Database: ${PROJECT_DIR}/data/options_intraday.db"
    echo "Backups:  ${PROJECT_DIR}/data/backups/"
    echo ""
else
    echo "Cancelled. No changes made."
fi
