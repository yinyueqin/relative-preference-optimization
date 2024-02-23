#!/bin/bash

# export OPENAI_API_KEY="your_api_key"

# Define the configuration paths
CONFIG_PATHS=(
    "/root/rpo-paired_llama2_7b_hh_all-MiniLM-L6-v2_0.25_2024-01-25_02-26-53_155161"
    "/root/rpo-paired_llama2_7b_hh_all-MiniLM-L6-v2_0.5_2024-01-25_05-28-45_370261"
)

# Loop through each configuration path
for CONFIG_PATH in "${CONFIG_PATHS[@]}"; do
    # Get the full model name from the configuration path
    FULL_MODEL_NAME=$(basename "$CONFIG_PATH")
    # Extract the model name from the full model name
    MODEL_NAME=$(echo "$FULL_MODEL_NAME" | sed 's/_\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\).*//')
    echo "$MODEL_NAME"

    # Run the python evaluation script with the current configuration path
    python eval.py \
        --config-path="$CONFIG_PATH"/ \
        ++mode=alpacaeval \
        ++model.eval_batch_size=32 \
        ++samples_dir=samples_alpaca/

    # Define the JSON file path
    JSON_FILE="samples_alpaca/alpaca_${FULL_MODEL_NAME}.json"

    # Check if the JSON file exists
    if [ -f "$JSON_FILE" ]; then
        # Run the alpaca evaluation with the JSON file
        alpaca_eval \
            --model_outputs "$JSON_FILE" \
            --annotators_config 'alpaca_eval_gpt4_turbo_fn' \
            --name "$MODEL_NAME"
    else
        # Print an error message if the JSON file does not exist
        echo "JSON not found: $JSON_FILE"
    fi
done