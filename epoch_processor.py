from relay_processor import RelayProcessor
from vote_processor import VoteProcessor
from sync_processor import SyncProcessor
import config as cfg

EPOCH_VOTE_DELAY = (cfg.SLACK_EPOCHS) * cfg.EPOCH_LENGTH
SYNC_DELAY = (cfg.VOTE_MAX_EPOCHS + cfg.SLACK_EPOCHS) * cfg.EPOCH_LENGTH
FINALIZE_DELAY = (
    cfg.SYNC_EPOCHS + cfg.VOTE_MAX_EPOCHS + cfg.SLACK_EPOCHS
) * cfg.EPOCH_LENGTH


class EpochProcessor:
    """class that handles the processing of everything for a particular epoch. makes a child processor for each stage of epoch processing"""

    def __init__(self, epoch):
        self.epoch = epoch
        self.cached_processes = []
        self.staged_cached_processes = []
        if self.time_alive > SYNC_DELAY:
            self.state = "sync"
            self.processor = SyncProcessor(self.epoch, None)
        elif self.time_alive > EPOCH_VOTE_DELAY:
            self.state = "vote"
            self.processor = VoteProcessor(self.epoch, set(), False)
        else:
            self.state = "relay"
            self.processor = RelayProcessor(self.epoch)

        if self.epoch not in cfg.epoch_chain_commit:
            cfg.epoch_chain_commit[cfg.chain_commitment(self.epoch, "ep")] = self.epoch

    def __del__(self):
        #deactivate seems not to work to turn off vote processors so this function added
        try:
            self.processor.execute = False
        except:
            pass
        self.processor = None

    @property
    def time_alive(self):
        """epochs since current epoch"""
        return cfg.current_epoch - self.epoch

    def step(self):
        """update processor at the end of each epoch"""
        if self.time_alive == FINALIZE_DELAY:
            # print("~done delay", self.epoch)
            self.processor.finalize_block()
            self.delete_reference()
        elif self.time_alive == SYNC_DELAY:
            # print("~sync delay", self.epoch)
            confirmed_bc = self.processor.terminate_vote()
            # print('~done terminate')
            self.processor = SyncProcessor(self.epoch, confirmed_bc)
            self.state = "sync"
        elif self.time_alive == EPOCH_VOTE_DELAY:
            # print("~vote delay", self.epoch)
            seen_bc = self.processor.seen_bc
            # print("~seen bc:",len(seen_bc))
            self.processor = VoteProcessor(self.epoch, seen_bc)
            self.state = "vote"
        self.cached_processes = self.staged_cached_processes.copy()
        self.staged_cached_processes = []
        self.execute_cached_processes()

    def delete_reference(self):
        """remove from memory"""
        cfg.finished_epoch_processes.add(self.epoch)

    def execute_new_process(self, state, func, *args):
        """respond to a message from a peer. if it should be processed next epoch then it is cached"""
        if state == self.state:
            func = self.find_func(func)
            func(*args)
        else:
            self.staged_cached_processes.append(
                {"state": state, "func": func, "args": args}
            )

    def execute_cached_processes(self):
        """execute all valid processes, delete otherwise"""
        for process in self.cached_processes:
            state = process["state"]
            func = process["func"]
            args = process["args"]
            if state == self.state:
                func = self.find_func(func)
                func(*args)

    def find_func(self, func):
        """given the type of process return the correct function of child processor"""
        if func == "block_request":
            func = self.processor.fulfill_block_request
        if func == "relay":
            func = self.processor.handle_relay
        if func == "bc_request":
            func = self.processor.fulfill_bc_request
        if func == "vote_request":
            func = self.processor.fulfill_vote_request
        return func
