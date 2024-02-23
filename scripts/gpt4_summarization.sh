#!/bin/bash

# Define the configuration paths
CONFIG_PATHS=(
    "/root/rpo-paired_llama2_7b_tldr_all-MiniLM-L6-v2_0.25_2024-01-24_12-46-26_630089"
    "/root/rpo-paired_llama2_7b_tldr_all-MiniLM-L6-v2_0.5_2024-01-24_04-09-19_840154"
)

# Loop through each configuration path
for CONFIG_PATH in "${CONFIG_PATHS[@]}"; do
    # Get the file name from the configuration path
    FILE_NAME=$(basename $CONFIG_PATH)

    # Run the python evaluation script with the current configuration path
    python eval.py \
        --config-path=$CONFIG_PATH \
        ++mode=sample \
        ++n_samples=256 \
        ++model.eval_batch_size=32

    # Define the JSON file path
    JSON_FILE="samples/${FILE_NAME}.json"

    # Run the python comparison script with the JSON file
    python compare.py \
        -f $JSON_FILE \
        -mc 256 \
        -bk chosen \
        -ck policy \
        -r ./results \
        -j gpt-4-0613 \
        -t summarization 
done