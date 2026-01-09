import os
import pandas as pd
import matplotlib.pyplot as plt
import sys
from pathlib import Path

# --- User-defined parameters ---
bin_size_seconds = 60
smoothing_window = 5

# --- Paths and setup ---
# Path for the first set of CSV files (Experiment 1)
csv_path_exp1 = 'input_full/metrics'
# Path for the second set of CSV files (Experiment 2)
csv_path_exp2 = 'input_ahp/metrics'
graph_path = 'output'

# The script now expects up to three command-line arguments:
# 1. Path for Experiment 1 CSVs
# 2. Path for Experiment 2 CSVs
# 3. Output path for graphs
if len(sys.argv) > 1:
    csv_path_exp1 = sys.argv[1]
    if len(sys.argv) > 2:
        csv_path_exp2 = sys.argv[2]
    if len(sys.argv) > 3:
        graph_path = sys.argv[3]

directory = Path(graph_path)
directory.mkdir(parents=True, exist_ok=True)

# --- Function to process and smooth data ---
def process_data(file_path, bin_size, smoothing_window):
    """Reads, bins, and smooths data from a CSV file."""
    df = pd.read_csv(file_path)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='ms')
    df.set_index('Timestamp', inplace=True)
    
    binned_df = df.resample(f'{bin_size}s').mean()
    binned_df['Smoothed_Value'] = binned_df['Value'].rolling(window=smoothing_window, min_periods=1).mean()
    
    return binned_df

def create_graph(filename, file_path_exp1, file_path_exp2):
    # Process data for both experiments
    binned_df_exp1 = process_data(file_path_exp1, bin_size_seconds, smoothing_window)
    binned_df_exp2 = process_data(file_path_exp2, bin_size_seconds, smoothing_window)
    
    # Calculate time elapsed in hours for each experiment independently, starting from its own first timestamp.
    start_time_exp1 = binned_df_exp1.index.min()
    binned_df_exp1['Time_Elapsed_Hours'] = (binned_df_exp1.index - start_time_exp1).total_seconds() / 3600
    
    start_time_exp2 = binned_df_exp2.index.min()
    binned_df_exp2['Time_Elapsed_Hours'] = (binned_df_exp2.index - start_time_exp2).total_seconds() / 3600
    
    # --- Plotting ---
    plt.figure(figsize=(12, 7))
    
    # Plot data for Experiment 1
    plt.plot(binned_df_exp1['Time_Elapsed_Hours'], binned_df_exp1['Smoothed_Value'], marker='', linestyle='-', color='red', label='AHP + KNN')
    
    # Plot data for Experiment 2
    plt.plot(binned_df_exp2['Time_Elapsed_Hours'], binned_df_exp2['Smoothed_Value'], marker='', linestyle='-', color='blue', label='AHP Only')
    
    # Set title and labels
    plt.title(f"{filename[:-4]}")
    plt.xlabel('Time Elapsed (Hours)')
    plt.ylabel('Value')
    
    # Add a legend
    plt.legend()
    
    # Use tight layout
    plt.tight_layout()
    
    # Save the plot
    output_filename = os.path.join(graph_path, filename[:-4] + '_comparison.png')
    plt.savefig(output_filename, bbox_inches='tight')
    
    plt.close()

# if True:
#     create_graph("cpu_diffs", "outputs_5h/outputs_simulation_5h_ahp_10/extra_metrics/CPU_Cores.csv", "outputs_5h/outputs_simulation_5h_ahp_10/metrics/total_cpu.csv")
#     exit(42)

# --- Main loop ---
for filename in os.listdir(csv_path_exp1):
    if filename.endswith('.csv'):
        file_path_exp1 = os.path.join(csv_path_exp1, filename)
        file_path_exp2 = os.path.join(csv_path_exp2, filename)
        
        # Check if the corresponding file exists in the second directory
        if os.path.exists(file_path_exp2):
            create_graph(filename, file_path_exp1, file_path_exp2)
            

print(f"Comparison graphs with aligned timelines have been created and saved at '{graph_path}/'")