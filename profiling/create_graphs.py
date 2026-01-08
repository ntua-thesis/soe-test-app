import os
import pandas as pd
import matplotlib.pyplot as plt
import sys
from pathlib import Path

# --- User-defined parameters ---
# Define the bin size in seconds for data aggregation
bin_size_seconds = 60 # e.g., 60 for 1-minute bins
# Define the smoothing window size (e.g., 5 for a 5-point rolling average)
smoothing_window = 5

# --- Paths and setup ---
csv_path = 'outputs_simulation/metrics'
graph_path = 'outputs_simulation/graphs'

if len(sys.argv) > 1:
    csv_path = sys.argv[1]
    if len(sys.argv) > 2:
        graph_path = sys.argv[2]

directory = Path(graph_path)
directory.mkdir(parents=True, exist_ok=True)

def calculate_stats_from_csv(filename):
    """
    Reads a CSV file, calculates the average and maximum of the 'Value' column,
    and returns a dictionary with the results.

    Args:
        filename (str): The path to the CSV file.

    Returns:
        dict: A dictionary containing 'average_value' and 'max_value',
              or None if an error occurs.
    """
    try:
        # Read the CSV file into a pandas DataFrame
        df = pd.read_csv(filename)
        
        # Check if the 'Value' column exists in the DataFrame
        if 'Value' in df.columns:
            # Calculate the mean (average) and max of the 'Value' column
            average_value = df['Value'].mean()
            max_value = df['Value'].max()
            sum = df['Value'].sum()
            return {'average_value': average_value, 'max_value': max_value, 'sum': sum}
        else:
            print(f"Error: 'Value' column not found in the file '{filename}'.")
            return None

    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred with '{filename}': {e}")
        return None

# --- Main loop ---
print("Starting data processing and graph generation...")
for filename in os.listdir(csv_path):
    if filename.endswith('.csv'):
        file_path = os.path.join(csv_path, filename)

        # Calculate and print both average and max values
        stats = calculate_stats_from_csv(filename=file_path)
        if stats:
            print(f"Stats for {filename}:")
            print(f"  Average Value: {stats['average_value']:.4f}")
            print(f"  Maximum Value: {stats['max_value']:.4f}")
            print(f"  Sum Value: {stats['sum']:.4f}")
        
        # Now, perform the plotting operations
        df = pd.read_csv(file_path)
        
        # Convert timestamp from milliseconds to datetime objects
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='ms')
        df.set_index('Timestamp', inplace=True)
        
        # 1. Create bins of n seconds
        # 'bin_size_seconds' defines the resampling frequency
        binned_df = df.resample(f'{bin_size_seconds}s').mean()
        
        # 2. Apply a rolling mean for smoothing
        # The 'rolling()' function with the 'smoothing_window' size calculates a moving average
        binned_df['Smoothed_Value'] = binned_df['Value'].rolling(window=smoothing_window, min_periods=1).mean()
        
        # --- Plotting ---
        plt.figure(figsize=(12, 7))
        
        # Plot the original binned data
        plt.plot(binned_df.index, binned_df['Value'], linestyle='--', alpha=0.5, label='Binned Data')
        
        # Plot the smoothed data
        plt.plot(binned_df.index, binned_df['Smoothed_Value'], marker='', linestyle='-', color='red', label='Smoothed Data')
        
        # Set title and labels
        plt.title(f"{filename[:-4]} - Binned and Smoothed")
        plt.xlabel('Timestamp')
        plt.ylabel('Value')
        
        # Add a legend to distinguish the lines
        plt.legend()
        
        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45)
        
        # Use tight layout to prevent labels from being cut off
        plt.tight_layout()
        
        # Save the plot
        output_filename = os.path.join(graph_path, filename[:-4] + '_smoothed.png')
        plt.savefig(output_filename, bbox_inches='tight')
        
        plt.close()

print(f"\nBinned and smoothed graphs have been created and saved at '{graph_path}/'")
print("All values have been processed and printed.")
