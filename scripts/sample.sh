#!/bin/bash

# Define the configuration paths
CONFIG_PATHS=(
    "/root/rpo-paired_llama2_7b_hh_all-MiniLM-L6-v2_0.25_2024-01-25_02-26-53_155161"
    "/root/rpo-paired_llama2_7b_hh_all-MiniLM-L6-v2_0.5_2024-01-25_05-28-45_370261"
)


# Loop through each configuration path
for CONFIG_PATH in "${CONFIG_PATHS[@]}"; do
    # Get the file name from the configuration path
    FILE_NAME=$(basename $CONFIG_PATH)

    # Run the python script with the current configuration path
    python eval.py \
        --config-path=$CONFIG_PATH \
        ++mode=sample \
        ++n_samples=256 \
        ++model.eval_batch_size=32 \
        ++samples_dir=examples/
done