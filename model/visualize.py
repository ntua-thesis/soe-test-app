import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 1. Load the Data
# If your file has a different name, change it here
try:
    df = pd.read_csv('compiled_dataset.csv')
except FileNotFoundError:
    print("Error: 'profiling_data.csv' not found. Please create the file first.")
    exit()

# 2. Set up the plotting style
sns.set_theme(style="whitegrid")
plt.figure(figsize=(12, 8))

# 3. Create the Scatter Plot
# X-axis: CPU Usage
# Y-axis: Latency P99
# Size: Target RPS (s parameter)
# Color: Success Rate (c parameter)

scatter = plt.scatter(
    x=df['cpu_per_limit_for_60s'], 
    y=df['latency_p99'], 
    s=df['target_rps'] * 2,  # Multiplied by 2 to make dots more visible
    c=df['success_rate'], 
    cmap='RdYlGn',           # Red (low success) to Green (high success)
    alpha=0.7,               # Transparency
    edgecolors='black',      # circle borders
    linewidth=0.5
)

# 4. Add Labels and Titles
plt.title('Application Profiling: CPU Load vs Latency', fontsize=16, pad=20)
plt.xlabel('CPU Usage (% of Limit over 60s)', fontsize=12)
plt.ylabel('Latency P99 (ms)', fontsize=12)

# 5. Add Colorbar for Success Rate
cbar = plt.colorbar(scatter)
cbar.set_label('Success Rate (1.0 = 100%)', rotation=270, labelpad=15)

# 6. Add a custom Legend for Size (RPS)
# We create dummy points to represent the sizes in the legend
sizes = [100, 300, 500] # Example sizes based on your data range
legend_markers = [plt.scatter([], [], s=s*2, c='gray', alpha=0.5, edgecolors='none') for s in sizes]
plt.legend(legend_markers, [f'{s} RPS' for s in sizes], title="Target RPS", loc='upper left')

# 7. Add Grid and Adjust Layout
plt.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()

# 8. Show or Save
plt.savefig('profiling_visualization.png') # Uncomment to save image
# plt.show()
