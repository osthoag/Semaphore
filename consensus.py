import config as cfg
import blocks as bk
import json
import os
from process import Process
import ast
import consensus as cs
import communications as cm


def reorg(highest_common_epoch, chain):
    old_epochs = sorted(cfg.blocks.keys())
    for epoch in old_epochs[old_epochs.index(highest_common_epoch) + 1 :]:
        del cfg.blocks[epoch]
        del cfg.hashes[epoch]
        cfg.epochs.pop(epoch)

    for epoch in sorted(chain.keys()):
        add_block(chain[epoch])


def load_block_data(block):
    """send block data to memory"""
    epoch = block["epoch_timestamp"]
    cfg.blocks[epoch] = block
    cfg.hashes[epoch] = bk.calc_block_hash(block)
    cfg.indexes[epoch] = block["block_index"]
    cfg.epochs.append(epoch)


def stage_history_update(block):
    """updates to make to block data at end of epoch"""
    cfg.staged_block_updates.append(block)


def add_block(block, epoch, sync_delay=False):
    """add a block to the chain"""
    block_epoch = block["epoch_timestamp"]
    # SANITY CHECK
    if block["chain_commitment"] != cfg.chain_commitment(epoch) or epoch != block_epoch:
        if epoch != block_epoch:
            print(f"something went very very wrong: epochs dont match")
        if block["chain_commitment"] != cfg.chain_commitment(epoch):
            print(f"something went very very wrong: chain commitments dont match")

    stage_history_update(block)

    dump = json.dumps(block)
    name = os.path.join(f"./{cfg.ALIAS}", f"{epoch}.json")
    with open(name, "wb") as f:
        f.write(dump.encode("utf-8"))


