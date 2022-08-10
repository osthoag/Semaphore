import hashlib
import json
from logging import raiseExceptions
from numpy import block

from pytz import common_timezones
import broadcasts as bc
import config as cfg


def sha_hash(preimage: str) -> str:
    """Calculate the sha256 hash of a preimage"""
    sha = hashlib.sha256
    return sha(preimage.encode()).hexdigest()


def build_block(broadcasts: list, epoch: int) -> block:
    """generates a valid block given a list of broadcasts valid in an epoch"""
    block = {}
    data = [bc.split_broadcast(broadcast) for broadcast in broadcasts]
    alias_list = [bc["alias"] for bc in data]
    bc_data = [bc["sig_image"] for bc in data]
    bc_data = [
        bc[: cfg.ALIAS_LEN] + bc[cfg.ALIAS_LEN + cfg.CHAIN_COMMIT_LEN :]
        for bc in bc_data
    ]  # removes chain commitment from each broadcast

    # sanity check:
    commit = cfg.chain_commitment(epoch, "bb").zfill(cfg.CHAIN_COMMIT_LEN)
    # print('~bb',commit)
    commits = [bc["chain_commit"] for bc in data]
    commits = set(commits)
    if len(commits) > 1:
        raise Exception("commits are not the same")
        
        # print('commits are not the same')
    try:
        c = commits.pop()
        if c != commit:
            raise Exception("commit doesnt match epoch commit")
    except:
        pass

    if len(broadcasts) > 0:
        bc_data = [broadcast for _, broadcast in sorted(zip(alias_list, bc_data))]
        sig_data = [bc["signature"] for bc in data]
        sig_data = [bc for _, bc in sorted(zip(alias_list, sig_data))]
        bc_tree = build_merkle_tree(bc_data)
        sig_tree = build_merkle_tree(sig_data)

        block["bc_root"] = bc_tree[0][0]
        block["sig_root"] = sig_tree[0][0]
        block["bc_body"] = bc_tree[-1]
        block["sig_body"] = sig_tree[-1]
    else:
        block["bc_root"] = "None"
        block["sig_root"] = "None"
        block["bc_body"] = "None"
        block["sig_body"] = "None"

    prev_epoch = epoch - cfg.SYNC_EPOCHS
    if prev_epoch not in cfg.epochs:
        past_epochs = [epoch for epoch in cfg.epochs if epoch < prev_epoch]
        prev_epoch = max(past_epochs)

    block["block_index"] = cfg.indexes[prev_epoch] + cfg.SYNC_EPOCHS
    block["chain_commitment"] = cfg.chain_commitment(epoch, "bk")
    block["epoch_timestamp"] = epoch

    return block


def calc_block_hash(block: block) -> str:
    """calculates the hash of a block"""
    if block == "GENESIS":
        return 'GENESIS'
    header_str = ""
    header_str += block["bc_root"]
    header_str += block["sig_root"]
    header_str += block["chain_commitment"]
    header_str += str(block["block_index"])
    header_str += str(block["epoch_timestamp"])
    return sha_hash(header_str)


def check_block_valid(block):
    """checks that all the contents of a block are valid"""
    return True


def check_chain_commitment(block):
    """checks that the chain commitment is valid and not in the future"""
    return True


def get_block_engagements(block: block) -> set:
    """returns a set of all aliases broadcasting in a block"""
    return {int(broadcast[: cfg.ALIAS_LEN]) for broadcast in block["bc_body"]}


def build_merkle_tree(data: list) -> list:
    '''builds a merkle tree from a list of elements'''
    if data == []:
        return []

    def tree_hash(base: list) -> list:
        base = [sha_hash(item) for item in base]
        if len(base) == 1:
            return [base]
        if len(base) % 2 == 1:
            base.append(base[-1])
        left = base[::2]
        right = base[1::2]
        new_layer = [left[i] + right[i] for i in range(len(left))]
        above_layers = tree_hash(new_layer)
        above_layers.append(base)
        return above_layers

    data = [str(item) for item in data]
    tree = tree_hash(data)
    tree.append(data)
    return tree


def construct_merkle_proof(tree: list, item: str) -> tuple:
    '''constructs a merkle path for a item in the tree'''
    if item not in tree[-1]:
        raise Exception(f"{item} not in data of {tree[0][0]}")
    data_index = tree[-1].index(item)
    index = data_index
    path = []
    for layer in tree[-2:0:-1]:
        if index % 2 == 0:
            path.append(layer[index + 1])
        else:
            path.append(layer[index - 1])
        index //= 2
    path.append(tree[0][0])
    return item, data_index, path


def verify_proof(proof:tuple)->bool:
    '''verifies a merkle proof'''
    item = proof[0]
    index = proof[1]
    path = proof[2]
    node = sha_hash(item)
    for sibling in path[:-1]:
        if index % 2 == 0:
            preimage = node + sibling
        else:
            preimage = sibling + node
        index //= 2
        node = sha_hash(preimage)
    return node == path[-1]

