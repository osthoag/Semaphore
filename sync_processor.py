import blocks as bk
import communications as cm
import consensus as cs
import config as cfg
import blocks as bk
import ast
import timing as tm
import sched
import time
import json, os
from process import Process


class SyncProcessor:
    """manages the block syncing process after epoch vote"""

    def __init__(self, epoch, broadcasts):
        self.epoch = epoch
        self.broadcasts = broadcasts

        if self.broadcasts is not None:
            self.block = bk.build_block(self.broadcasts, self.epoch)
        else:
            self.block = "no_block"
            self.block_votes = {}
            self.received_blocks = {}

        if self.block == "no_block":
            self.discover_new_block()

    def discover_new_block(self):
        """request most recent block from all peers"""
        for alias in cfg.peers:
            Process(
                1,
                SyncProcessor.format_block_response,
                self.conclude_block_process,
                "block_request",
                self.epoch,
                True,
                specific_peers=[alias],
            )

    def fulfill_block_request(self, alias, query_id):
        """send epoch's block to requesting peer"""
        # if self.block == "no_block":
        # print("~sending no_block", self.epoch, cfg.epoch_processes.keys())
        cm.send_peer_message(alias, f"query_fulfillment|{query_id}|{self.block}")

    @staticmethod
    def format_block_response(query, response):
        """format received string to dict"""
        if response == "no_block":
            return response
        received_block = ast.literal_eval(response)
        if type(received_block) is dict:
            return received_block

    def conclude_block_process(self, process):
        """incorporate information from block request"""
        block = process.cached_responses[0]
        if block == "no_block":
            bcid = "no_block"
        else:
            bcid = bk.calc_block_hash(block)

        if bcid in self.received_blocks:
            self.block_votes[bcid] += 1
        else:
            self.block_votes[bcid] = 1
            self.received_blocks[bcid] = block

    def finalize_block(self):
        """add final block to chain"""
        if self.block == "no_block":
            sorted_blocks = [
                bcid
                for bcid, _ in sorted(
                    self.block_votes.items(), key=lambda item: item[1]
                )
            ]
            if len(sorted_blocks) > 0:
                bcid = sorted_blocks[-1]
                self.block = self.received_blocks[bcid]
        if self.block == "no_block":
            self.block = bk.build_block({}, self.epoch)
            cfg.chain_commitment(self.epoch, "sn")
        cs.add_block(self.block, self.epoch)
        print("~hash", bk.calc_block_hash(self.block))
        print("~bkep", self.block["epoch_timestamp"])
        print(
            "~len ",
            len(self.block["bc_body"]) if self.block["bc_body"] != "None" else 0,
        )


class InitSyncProcessor:
    def __init__(self) -> None:
        self.request_history()

    def discover_new_block(self):
        """request most recent block from all peers"""
        Process(
            1,
            SyncProcessor.format_block_response,
            self.conclude_block_process,
            "block_request",
            cfg.epochs[-1] + cfg.EPOCH_LENGTH,
            True,
        )

    # def fulfill_block_request(self, alias, query_id):
    #     """send epoch's block to requesting peer"""
    #     cm.send_peer_message(alias, f"query_fulfillment|{query_id}|{self.block}")

    @staticmethod
    def format_block_response(query, response):
        """format received string to dict"""
        if response == "no_block":
            return response
        received_block = ast.literal_eval(response)
        if type(received_block) is dict:
            return received_block

    def conclude_block_process(self, process):
        """incorporate information from block request"""
        received_blocks = {}
        block_votes = {}

        for block in process.cached_responses:
            if block == "no_block":
                bcid = "no_block"
            else:
                bcid = bk.calc_block_hash(block)

            if bcid in received_blocks:
                block_votes[bcid] += 1
            else:
                block_votes[bcid] = 1
                received_blocks[bcid] = block
            sorted_bcids = [
                bcid
                for bcid, _ in sorted(block_votes.items(), key=lambda item: item[1])
            ]
            block = received_blocks[sorted_bcids[-1]]

            if block == "no_block":
                block = bk.build_block({}, cfg.epochs[-1] + cfg.EPOCH_LENGTH)

            if block["chain_commitment"] == cfg.chain_commitment(
                cfg.epochs[-1] + cfg.EPOCH_LENGTH
            ):
                tm.activate()
            else:
                self.discover_new_block()

    #########
    def request_history(self):
        chain_tip_epoch = cfg.epochs[-1]
        chain_tip_block = cfg.blocks[chain_tip_epoch]
        chain_tip_hash = bk.calc_block_hash(chain_tip_block)
        Process(
            1,
            InitSyncProcessor.format_history_response,
            self.conclude_history_process,
            "history_request",
            (chain_tip_epoch, chain_tip_hash),
            True,
        )
        print("~tip", chain_tip_epoch)

    def fulfill_history_request(self, alias, query_id, chain_tip_epoch, chain_tip_hash):
        """send block history to requesting peer"""
        if chain_tip_epoch not in cfg.epochs:
            print("~no block from epoch", chain_tip_epoch)
            return
        if chain_tip_hash != bk.calc_block_hash(cfg.blocks[chain_tip_epoch]):
            print("~block from alternate chain")
            return

        index = cfg.epochs.index(chain_tip_epoch) + 1
        history_epochs = cfg.epochs[index:]
        history_blocks = [cfg.blocks[epoch] for epoch in history_epochs]
        cm.send_peer_message(alias, f"query_fulfillment|{query_id}|{history_blocks}")

    @staticmethod
    def format_history_response(query, response):
        """format received string to list of dicts"""
        # print("~lenresp", len(response))
        if response == "no_block":
            return response
        received_blocks = ast.literal_eval(response)
        if type(received_blocks) is list:
            for block in received_blocks:
                if type(block) is not dict:
                    return
            return received_blocks

    def conclude_history_process(self, process):
        #!!!!MUST MAKE SURE THAT BLOCKS DONT GET ADDED MULTIPLE TIMES BY MULTIPLE PROCESSES!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        """incorporate information from history request"""
        # start = time.time()
        blocks = process.cached_responses[0]
        for block in blocks:
            if not bk.check_block_valid(block):
                print("bad block")
                return

        for block in blocks:
            epoch = block["epoch_timestamp"]
            cs.load_block_data(block)
            dump = json.dumps(block)
            name = os.path.join(f"./{cfg.ALIAS}", f"{epoch}.json")
            with open(name, "wb") as f:
                f.write(dump.encode("utf-8"))
        self.discover_new_block()
        # print("~elapsed", time.time() - start)
        # print(block['epoch_timestamp'])
        # cs.add_block(block,block['epoch_timestamp'])

