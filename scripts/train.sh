#!/bin/bash

# Define datasets and models
datasets=("hh" "tldr")
models=("llama7b" "llama13b" "mistral7b")

# SFT training loop
for dataset in "${datasets[@]}"; do
    for model in "${models[@]}"; do
        exp_name="sft_${dataset}_${model}"
        python train.py \
            --loss=sft \
            --model=${model} \
            --datasets="['${dataset}']" \
            --exp_name=${exp_name} \
            --mode=train \
            --cache_dir=.cache/
    done
done

# Baseline alignment training methods
methods=("ppo" "ipo" "dpo" "kto")

for method in "${methods[@]}"; do
    for dataset in "${datasets[@]}"; do
        for model in "${models[@]}"; do
            exp_name="${method}_${dataset}_${model}"
            python train.py \
                --loss=${method} \
                --model=${model} \
                --datasets="['${dataset}']" \
                --exp_name=${exp_name} \
                --mode=train \
                --cache_dir=.cache/ \
                --model.load_from=".cache/root/sft_${dataset}_${model}_2024-01-24_03-52-18_429394/LATEST/policy.pt"
        done
    done
done

# RPO Training configuration
losses=("rpo-paired" "rpo-unpaired")
distance_temperatures=("0.25" "0.5" "0.75")
sentence_transformers=("all-MiniLM-L6-v2" "sentence-t5-large")

for loss in "${losses[@]}"; do
    for dis_temp in "${distance_temperatures[@]}"; do
        for sen_trans in "${sentence_transformers[@]}"; do
            for dataset in "${datasets[@]}"; do
                for model in "${models[@]}"; do
                    exp_name="${loss}_${model}_${dataset}_${sen_trans}_${dis_temp}"
                    python train.py \
                        --loss=${loss} \
                        --model=${model} \
                        --datasets="['${dataset}']" \
                        --exp_name=${exp_name} \
                        --mode=train \
                        --cache_dir=.cache/ \
                        --model.load_from=".cache/root/sft_${dataset}_${model}_2024-01-24_03-52-18_429394/LATEST/policy.pt" \
                        --loss.distance_temperature=${dis_temp} \
                        --loss.sentence_transformer_name_or_path=${sen_trans}
                done
            done
        done
    done
done
