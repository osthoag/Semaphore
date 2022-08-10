import config as cfg
import ast
import communications as cm
from process import Process
import blocks as bk

reorg_processes = []


def request_fork_history(alias):
    index = cfg.MINIMUM_REORG_DEPTH
    past_epochs = []
    while True:
        try:
            past_epochs.append(cfg.epochs[-index])
            index *= 2
        except:
            break

    past_commits = [cfg.chain_commitment(epoch) for epoch in past_epochs]

    Process(
        1,
        format_fork_request,
        conclude_fork_process,
        "fork_request",
        past_commits,
        True,
        specific_peers=[alias],
    )


def fulfill_fork_request(alias, query_id, past_commits):
    print(past_commits)
    if past_commits[0] in cfg.epoch_chain_commit.keys():
        return
    else:
        print(f"~{past_commits[0] } no match")
    index = 0
    for commit in past_commits[1:]:
        if commit in cfg.epoch_chain_commit.keys():
            print(f"~{commit} match")
            shared_epoch = cfg.epoch_chain_commit[commit]
            index = cfg.epochs.index(shared_epoch)
            break

    history_epochs = cfg.epochs[index:]
    history_blocks = [cfg.blocks[epoch] for epoch in history_epochs]
    cm.send_peer_message(alias, f"query_fulfillment|{query_id}|{history_blocks}")


def format_fork_request(query, response):
    received_blocks = ast.literal_eval(response)
    if type(received_blocks) is list:
        for block in received_blocks:
            if type(block) is not dict:
                return
        return received_blocks


def conclude_fork_process(process):
    blocks = process.cached_responses[0]
    for block in blocks:
        if not bk.check_block_valid(block):
            print("bad block")
            return

    for block in blocks:
        epoch = block["epoch_timestamp"]
        block_hash = bk.calc_block_hash(block)
        if cfg.hashes[epoch] == block_hash:
            blocks = blocks[1:]
        else:
            break
    compare_weight(blocks, epoch)


def compare_weight(self, alt_headers, alt_blocks, common_header):
    alt_headers_copy = alt_headers.copy()
    common_index = self.headers.index(common_header)
    chain_engagements_canonical = set()
    chain_engagements_alt = set()
    canonical_headers = self.headers[common_index:]
    canonical_time, canonical_block = self.find_shallow_block(
        canonical_headers, self.blocks
    )
    alt_time, alt_block = self.find_shallow_block(alt_headers_copy, alt_blocks)

    while True:
        if canonical_time > alt_time:
            pre_engagements = self.parent.block_manager.get_block_engagements(
                canonical_block
            )
            for alias in pre_engagements:
                if alias not in chain_engagements_alt:
                    chain_engagements_canonical.add(alias)
            canonical_time, canonical_block = self.find_shallow_block(
                canonical_headers, self.blocks
            )

        elif alt_time > canonical_time:
            pre_engagements = self.parent.block_manager.get_block_engagements(alt_block)
            for alias in pre_engagements:
                if alias not in chain_engagements_canonical:
                    chain_engagements_alt.add(alias)
            alt_time, alt_block = self.find_shallow_block(alt_headers_copy, alt_blocks)

        else:
            canonical_pre_engagements = self.parent.block_manager.get_block_engagements(
                canonical_block
            )
            canonical_pre_engagements = {
                alias
                for alias in canonical_pre_engagements
                if alias not in chain_engagements_alt
            }
            alt_pre_engagements = self.parent.block_manager.get_block_engagements(
                alt_block
            )
            alt_pre_engagements = {
                alias
                for alias in alt_pre_engagements
                if alias not in chain_engagements_canonical
            }
            for alias in canonical_pre_engagements:
                chain_engagements_canonical.add(alias)
            for alias in alt_pre_engagements:
                chain_engagements_alt.add(alias)

            canonical_time, canonical_block = self.find_shallow_block(
                canonical_headers, self.blocks
            )
            alt_time, alt_block = self.find_shallow_block(alt_headers_copy, alt_blocks)

        if canonical_time == -1 and alt_time == -1:
            break

    if len(chain_engagements_canonical) < len(chain_engagements_alt):
        common_index = self.headers.index(common_header)
        for header in self.headers[common_header:]:
            del self.blocks[header]
        self.headers[common_index:] = alt_headers
        for header in alt_blocks:
            self.blocks[header] = alt_blocks[header]

