#!/bin/bash
# Run all test scenarios and generate separate HTML reports for comparison

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/reports/test_scenarios"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== NVDA Earnings Vol Analysis - Test Scenario Runner ==="
echo "Output directory: ${OUTPUT_DIR}"
echo ""

# Create output directory
mkdir -p "${OUTPUT_DIR}"

# Define all test scenarios
SCENARIOS=(
    "baseline"
    "high_vol"
    "low_vol"
    "gamma_unbalanced"
    "term_inverted"
    "flat_term"
    "negative_event_var"
    "extreme_front_premium"
    "sparse_chain"
)

# Track results
declare -A RESULTS
declare -A DURATIONS

# Run each scenario
for scenario in "${SCENARIOS[@]}"; do
    echo "----------------------------------------"
    echo "Running scenario: ${scenario}"
    
    output_file="${OUTPUT_DIR}/${scenario}_${TIMESTAMP}.html"
    
    start_time=$(date +%s)
    
    if python3 -m nvda_earnings_vol.main \
        --test-data \
        --test-scenario "${scenario}" \
        --output "${output_file}"; then
        
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        
        RESULTS["${scenario}"]="✓ SUCCESS"
        DURATIONS["${scenario}"]="${duration}s"
        
        echo "  ✓ Generated: ${output_file} (${duration}s)"
    else
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        
        RESULTS["${scenario}"]="✗ FAILED"
        DURATIONS["${scenario}"]="${duration}s"
        
        echo "  ✗ FAILED after ${duration}s"
    fi
    echo ""
done

# Generate summary report
echo "========================================"
echo "=== Test Scenario Summary ==="
echo "========================================"
echo ""

success_count=0
fail_count=0

for scenario in "${SCENARIOS[@]}"; do
    status="${RESULTS[${scenario}]}"
    duration="${DURATIONS[${scenario}]}"
    
    printf "%-25s %s (%s)\n" "${scenario}:" "${status}" "${duration}"
    
    if [[ "${status}" == "✓ SUCCESS" ]]; then
        ((success_count++))
    else
        ((fail_count++))
    fi
done

echo ""
echo "========================================"
echo "Results: ${success_count} passed, ${fail_count} failed"
echo "Output directory: ${OUTPUT_DIR}"
echo "========================================"

# Create index.html for easy navigation
index_file="${OUTPUT_DIR}/index_${TIMESTAMP}.html"
cat > "${index_file}" << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>NVDA Test Scenarios - Comparison Index</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 40px auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #76b900;
            padding-bottom: 10px;
        }
        .scenario-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }
        .scenario-card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .scenario-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        .scenario-card.success {
            border-left: 4px solid #76b900;
        }
        .scenario-card.failed {
            border-left: 4px solid #dc3545;
            opacity: 0.7;
        }
        .scenario-title {
            font-size: 18px;
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }
        .scenario-status {
            font-size: 14px;
            margin-bottom: 12px;
        }
        .scenario-status .success { color: #76b900; }
        .scenario-status .failed { color: #dc3545; }
        .scenario-desc {
            font-size: 13px;
            color: #666;
            margin-bottom: 15px;
            line-height: 1.4;
        }
        .view-link {
            display: inline-block;
            padding: 8px 16px;
            background: #76b900;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 14px;
            transition: background 0.2s;
        }
        .view-link:hover {
            background: #5a8f00;
        }
        .view-link.disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .summary {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .summary-item {
            display: inline-block;
            margin-right: 30px;
            font-size: 16px;
        }
        .summary-item .value {
            font-weight: 600;
            font-size: 24px;
        }
        .summary-item.success .value { color: #76b900; }
        .summary-item.failed .value { color: #dc3545; }
    </style>
</head>
<body>
    <h1>NVDA Earnings Volatility Analysis - Test Scenarios</h1>
    <p>Generated: TIMESTAMP_PLACEHOLDER</p>
    
    <div class="summary">
        <div class="summary-item success">
            <div class="value">SUCCESS_COUNT_PLACEHOLDER</div>
            <div>Passed</div>
        </div>
        <div class="summary-item failed">
            <div class="value">FAIL_COUNT_PLACEHOLDER</div>
            <div>Failed</div>
        </div>
        <div class="summary-item">
            <div class="value">TOTAL_COUNT_PLACEHOLDER</div>
            <div>Total</div>
        </div>
    </div>
    
    <div class="scenario-grid">
EOF

# Add each scenario to the index
for scenario in "${SCENARIOS[@]}"; do
    status="${RESULTS[${scenario}]}"
    duration="${DURATIONS[${scenario}]}"
    
    # Get scenario description from Python
    description=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from nvda_earnings_vol.data.test_data import TEST_SCENARIOS
print(TEST_SCENARIOS['${scenario}'].get('description', 'No description'))
" 2>/dev/null || echo "Description unavailable")
    
    if [[ "${status}" == "✓ SUCCESS" ]]; then
        card_class="success"
        link_html="<a href=\"${scenario}_${TIMESTAMP}.html\" class=\"view-link\" target=\"_blank\">View Report</a>"
    else
        card_class="failed"
        link_html="<span class=\"view-link disabled\">Report Unavailable</span>"
    fi
    
    cat >> "${index_file}" << EOF
        <div class="scenario-card ${card_class}">
            <div class="scenario-title">${scenario}</div>
            <div class="scenario-status">
                <span class="${card_class}">${status}</span> (${duration})
            </div>
            <div class="scenario-desc">${description}</div>
            ${link_html}
        </div>
EOF
done

# Close HTML
cat >> "${index_file}" << 'EOF'
    </div>
</body>
</html>
EOF

# Replace placeholders in index.html
sed -i "s/TIMESTAMP_PLACEHOLDER/${TIMESTAMP}/g" "${index_file}"
sed -i "s/SUCCESS_COUNT_PLACEHOLDER/${success_count}/g" "${index_file}"
sed -i "s/FAIL_COUNT_PLACEHOLDER/${fail_count}/g" "${index_file}"
sed -i "s/TOTAL_COUNT_PLACEHOLDER/$((success_count + fail_count))/g" "${index_file}"

echo ""
echo "Created index: ${index_file}"
echo ""

# Optional: Open in browser
if command -v xdg-open &> /dev/null; then
    echo "Opening index in browser..."
    xdg-open "${index_file}"
elif command -v open &> /dev/null; then
    echo "Opening index in browser..."
    open "${index_file}"
fi

echo "Done!"
