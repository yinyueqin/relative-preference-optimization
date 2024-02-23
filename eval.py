# Copyright (c) 2023 Contextual AI, Inc.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import torch
torch.backends.cuda.matmul.allow_tf32 = True
import transformers
from transformers import set_seed
from utils import disable_dropout, init_distributed, get_open_port, rank0_print
import os
import hydra
import torch.multiprocessing as mp
from omegaconf import OmegaConf, DictConfig
import json
import socket
from typing import Optional, Set
from trainers import BasicTrainer
import dataloader
from datetime import datetime
import trainers


@hydra.main(version_base=None, config_path="config", config_name="config")
def main(config: DictConfig):
    """Main entry point for evaluating. Validates config, loads model(s), and kicks off worker process(es)."""
    # Resolve hydra references, e.g. so we don't re-compute the run directory
    OmegaConf.resolve(config)
    print(OmegaConf.to_yaml(config))

    if config.mode not in ['sample', 'eval', 'alpacaeval']:
        raise Exception("This is a script for eval/sampling. config.mode should be one of 'sample', 'eval', or 'alpacaeval'")

    set_seed(config.seed)

    print('=' * 80)
    print(f'Writing to', config.samples_dir)
    print('=' * 80)

    # purely inference, so put as much as possible onto the first gpu
    model_kwargs = {'device_map': "balanced_low_0"} 

    tokenizer_name_or_path = config.local_run_dir or config.model.tokenizer_name_or_path # first see if saved tokenizer is in the experiment directory
    print(f'Loading tokenizer at {tokenizer_name_or_path}')
    tokenizer = transformers.AutoTokenizer.from_pretrained(tokenizer_name_or_path)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    print('building policy')
    policy_dtype = getattr(torch, config.model.policy_dtype)
    policy = transformers.AutoModelForCausalLM.from_pretrained(
        config.model.name_or_path, low_cpu_mem_usage=True, use_flash_attention_2=config.model.use_flash_attention, torch_dtype=policy_dtype, **model_kwargs)
    # note that models were only resized for csft before saving
    # important because number of tokens in pretrained tokenizer is different from model.config.vocab_size, 
    # so resizing at eval will throw an error if not resized before training
    if config.loss.name == 'csft':
        policy.resize_token_embeddings(len(tokenizer)) # model being loaded should already be trained with additional tokens for this to be valid
    disable_dropout(policy)
  
    # saved policy can be force set to null to sample from pretrained model
    if config.saved_policy is not None:
        state_dict = torch.load(os.path.join(config.cache_dir, config.saved_policy), map_location='cpu')
        step, metrics = state_dict['step_idx'], state_dict['metrics']
        print(f'loading pre-trained weights for policy at step {step} from {config.saved_policy} with metrics {json.dumps(metrics, indent=2)}')
        policy.load_state_dict(state_dict['state'])
    
    if config.mode == 'eval' and config.loss.use_reference_model:
        print('building reference model')
        reference_model_dtype = getattr(torch, config.model.reference_dtype)
        reference_model = transformers.AutoModelForCausalLM.from_pretrained(
            config.model.name_or_path, low_cpu_mem_usage=True, use_flash_attention_2=config.model.use_flash_attention, torch_dtype=reference_model_dtype, **model_kwargs)
        if config.loss.name == 'ppo':
            reference_model.resize_token_embeddings(len(tokenizer))
        disable_dropout(reference_model)

        if config.model.load_from is not None:
            state_dict = torch.load(os.path.join(config.cache_dir, config.model.load_from), map_location='cpu')
            step, metrics = state_dict['step_idx'], state_dict['metrics']
            print(f'loading pre-trained weights for reference at step {step} from {config.model.load_from} with metrics {json.dumps(metrics, indent=2)}')
            reference_model.load_state_dict(state_dict['state'])
    else:
        reference_model = None
    
    data_loader_class = getattr(dataloader, config.loss.dataloader)
    data_iterator_kwargs = dict(
        max_length=config.model.max_length,
        max_prompt_length=config.model.max_prompt_length,
        # since the human/asst fields are not in the configs of the already-released models, add defaults
        human_prefix=config['human_prefix'],
        human_suffix=config['human_suffix'],
        assistant_prefix=config['assistant_prefix'],
        assistant_suffix=config['assistant_suffix'],
        seed=config.seed,
        # the following kwargs can be used to make dataset imbalanced (only used by UnbalancedUnpairedPreferenceDataLoader)
        frac_unique_desirable=config.get('frac_unique_desirable', 1.0),
        frac_unique_undesirable=config.get('frac_unique_undesirable', 1.0),
        # control tokens taken from Korbak et al.'s (2023) "Pretraining Models with Human Feedback"
        # SFTDataLoader will use them for sampling; ConditionalSFTDataLoader for training
        chosen_control_token=(config.loss.chosen_control_token if config.loss.name == "csft" else None),
        rejected_control_token=(config.loss.rejected_control_token if config.loss.name == "csft" else None),
    )

    if config.mode == 'sample':
        print(f'Loading dataloader')
        os.makedirs(config.samples_dir, exist_ok=True)

        # use the SFT dataloader because we don't want to repeat prompts
        # and bc data ordering is different in paired vs unpaired data loaders
        eval_iterator = dataloader.SFTDataLoader(
            config.datasets, 
            tokenizer,
            split='test',
            batch_size=config.model.eval_batch_size,
            n_examples=config.n_samples,
            max_prompt_count=1,
            **data_iterator_kwargs
        )

        TrainerClass = getattr(trainers, config.loss.trainer)
        trainer = TrainerClass(tokenizer, config, None, eval_iterator, policy, reference_model=reference_model)
        samples = trainer.sample()
        fn = os.path.join(config.samples_dir, f'{os.path.basename(config.local_run_dir)}.json')
        json.dump({
            'sampled_at' : str(datetime.now()),
            'config' : OmegaConf.to_container(config, resolve=True),
            'samples' : samples,
        }, open(fn, 'w'), indent=2)
    elif config.mode == 'eval':
        print(f'Loading dataloader')
        eval_iterator = data_loader_class(
            config.datasets, 
            tokenizer,
            split='test',
            batch_size=config.model.eval_batch_size,
            n_examples=config.n_eval_examples,
            n_epochs=(1 if config.n_eval_examples is None else None),
            **data_iterator_kwargs
        )
        TrainerClass = getattr(trainers, config.loss.trainer)
        trainer = TrainerClass(tokenizer, config, None, eval_iterator, policy, reference_model=reference_model)
        results = trainer.eval() 
        rank0_print(results)
    elif config.mode == 'alpacaeval':
        print(f'Loading dataloader')
        os.makedirs(config.samples_dir, exist_ok=True)

        eval_iterator = dataloader.SFTDataLoader(
            ['alpacaeval'], 
            tokenizer,
            split='test',
            batch_size=config.model.eval_batch_size,
            n_examples=None,
            n_epochs=1,
            **data_iterator_kwargs
        )

        TrainerClass = getattr(trainers, config.loss.trainer)
        trainer = TrainerClass(tokenizer, config, None, eval_iterator, policy, reference_model=reference_model)
        samples = trainer.sample(include_original_prompt=True)

        alpaca_formatted_examples = []
        for sample in samples:
            alpaca_formatted_examples.append({
                'instruction' : sample['original_prompt'],
                'output': sample['policy'].strip(),
                'reference' : sample['chosen'].strip(),
            })
        
        fn = os.path.join(config.samples_dir, f'alpaca_{os.path.basename(config.local_run_dir)}.json')
        json.dump(alpaca_formatted_examples, open(fn, 'w'), indent=2)
    else:
        raise Exception("mode is neither sample nor eval")


if __name__ == '__main__':
    main()