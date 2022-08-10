from sqlalchemy import false
import config as cfg
import sched
import time
import clock as cl
import communications as cm
import consensus as cs
from epoch_processor import EpochProcessor
from threading import Thread

TEST_SEND_BROADCASTS = True


def time_events():
    """
    Executes actions on ticks of the clock, including at start of epoch
    
    The event loop runs continuously on its own thread managing time synchronization, epoch tracking, and . 
    """

    s = sched.scheduler(time.time, time.sleep)

    def event_loop():
        """functions that execute on a timer with epochs"""
        offset = 0
        now = cfg.network_time()
        offset = now % cfg.CLOCK_INTERVAL
        if cfg.CLOCK_INTERVAL - offset < cfg.CLOCK_INTERVAL / 2:
            offset -= cfg.CLOCK_INTERVAL
        cl.initiate_time_update()
        s.enter((cfg.CLOCK_INTERVAL - offset), 0, event_loop)

        Thread(target=run_epoch).start()

    s.enter(0, 0, event_loop)
    s.run()


def run_epoch():
    now = cfg.network_time()
    if round(now, 2) % cfg.EPOCH_LENGTH == 0:
        next_epoch = cfg.current_epoch + cfg.FORWARD_SLACK_EPOCHS * cfg.EPOCH_LENGTH
        print()
        # global prev
        # try:
        #     print("~elpased", time.time() - prev)
        # except:
        #     pass
        # prev = time.time()
        print("~EPOCH", cfg.current_epoch)

        if cfg.activated:
            for epoch in cfg.epoch_processes:
                cfg.epoch_processes[epoch].step()
            if cfg.current_epoch > 0:
                if TEST_SEND_BROADCASTS and cfg.current_epoch > 0:
                    for i in range(1):
                        cm.originate_broadcast(f"{cfg.ALIAS}{i}{cfg.network_time()}")
                if (
                    next_epoch not in cfg.epoch_processes
                ):  # TODO do something better than this check
                    start_epoch_process(next_epoch)
                for epoch in cfg.finished_epoch_processes:
                    # print('~del',epoch)
                    del cfg.epoch_processes[epoch]
                cfg.finished_epoch_processes = set()
                load_staged_updates()

        cfg.current_epoch = round(now) + 1


def load_staged_updates():
    for block in cfg.staged_block_updates:
        cs.load_block_data(block)
        ep = block["epoch_timestamp"]
    cfg.staged_block_updates = []


def start_epoch_process(epoch=cfg.current_epoch):
    """initiate new epoch process"""
    if epoch in cfg.epoch_processes:
        print("something went very wrong. epoch process already exists")
    cfg.epoch_processes[epoch] = EpochProcessor(epoch)


def activate():
    print("EPOCH PROCESSING ACTIVATED")
    PAST = cfg.SYNC_EPOCHS + cfg.VOTE_MAX_EPOCHS + cfg.SLACK_EPOCHS
    FUTURE = cfg.FORWARD_SLACK_EPOCHS + 1
    activating_epochs = range(
        cfg.current_epoch - PAST * cfg.EPOCH_LENGTH,
        cfg.current_epoch + FUTURE * cfg.EPOCH_LENGTH,
        cfg.EPOCH_LENGTH,
    )
    for epoch in activating_epochs:
        start_epoch_process(epoch)

    cfg.activated = True

def deactivate():
    print("EPOCH PROCESSING HALTED")
    PAST = cfg.SYNC_EPOCHS + cfg.VOTE_MAX_EPOCHS + cfg.SLACK_EPOCHS
    FUTURE = cfg.FORWARD_SLACK_EPOCHS
    activated_epochs = range(
        cfg.current_epoch - PAST * cfg.EPOCH_LENGTH,
        cfg.current_epoch + FUTURE * cfg.EPOCH_LENGTH,
        cfg.EPOCH_LENGTH,
    )
    for epoch in activated_epochs:
        del cfg.epoch_processes[epoch]
    for epoch in cfg.finished_epoch_processes:
        del cfg.epoch_processes[epoch]

    cfg.activated = False