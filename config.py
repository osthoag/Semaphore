import socket, json
from alias_management import get_claimed_aliases
import random
import time

with open("params.json") as f:
    params = json.load(f)
ALIAS_LEN = params["ALIAS_LEN"]
SIG_LEN = params["SIG_LEN"]
CHAIN_COMMIT_LEN = params["CHAIN_COMMIT_LEN"]
INDICATOR_LEN = params["INDICATOR_LEN"]
HEADER_LENGTH = params["HEADER_LENGTH"]
TIME_BASE_OFFSET = params["TIME_BASE_OFFSET"]# + random.random() * 10
CLOCK_INTERVAL = params["CLOCK_INTERVAL"]
EPOCH_LENGTH = params["EPOCH_LENGTH"]
SLACK_EPOCHS = params["SLACK_EPOCHS"]
FORWARD_SLACK_EPOCHS = params["FORWARD_SLACK_EPOCHS"]
TIME_SAMPLE_NUM = params["TIME_SAMPLE_NUM"]
TIME_INERTIA = params["TIME_INERTIA"]
TIME_PROCESS_DURATION = params["TIME_PROCESS_DURATION"]
LOCAL_WEIGHT = params["LOCAL_WEIGHT"]
TIME_ERROR_THRESHOLD = params["TIME_ERROR_THRESHOLD"]
REPORT_ERROR_THRESHOLD = params["REPORT_ERROR_THRESHOLD"]
EXTRA_CORRECTION_DRIFT = params["EXTRA_CORRECTION_DRIFT"]
SAFETY_FACTOR = params["SAFETY_FACTOR"]
VOTE_INIT_CONF = params["VOTE_INIT_CONF"]
VOTE_INIT_CONF_NEG = params["VOTE_INIT_CONF_NEG"]
VOTE_SAMPLE_NUM = params["VOTE_SAMPLE_NUM"]
VOTE_CONSENSUS_LEVEL = params["VOTE_CONSENSUS_LEVEL"]
VOTE_CERTAINTY_LEVEL = params["VOTE_CERTAINTY_LEVEL"]
VOTE_MAX_EPOCHS = params["VOTE_MAX_EPOCHS"]
VOTE_ROUND_TIME = params["VOTE_ROUND_TIME"]
SYNC_EPOCHS = params["SYNC_EPOCHS"]
MINIMUM_REORG_DEPTH = params["MINIMUM_REORG_DEPTH"]

DELAY = SLACK_EPOCHS + VOTE_MAX_EPOCHS + FORWARD_SLACK_EPOCHS + SYNC_EPOCHS + 1
CHAIN_COMMIT_LEN = 64 * DELAY

ALIAS = 0
IP = socket.gethostbyname(socket.gethostname() + ".local")
PORT = 0

pk = 0
sk = 0
alias_keys = get_claimed_aliases()

peers = {}
all_speaking = {}
all_listening = {}

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
network_offset = 0



activated = False
current_epoch = 0
epoch_processes = {}
finished_epoch_processes = set()
staged_block_updates = []

epoch_chain_commit = {}  # {chain_commit:epoch}

GENESIS = range(DELAY * 2-1)
blocks = {i: "GENESIS" for i in GENESIS}  # {epoch: block}
epochs = [i * EPOCH_LENGTH for i in GENESIS]
hashes = {i * EPOCH_LENGTH: str(i) for i in GENESIS}  # {epoch: hash}
indexes = {i * EPOCH_LENGTH: i for i in GENESIS}  # {epoch: index}

def network_time():
    return time.time() + network_offset

def chain_commitment(epoch, where=None):
    earliest_process_epoch = (
        current_epoch
        - (SLACK_EPOCHS + VOTE_MAX_EPOCHS + SYNC_EPOCHS) * EPOCH_LENGTH
    )
    last_commit_epoch = epoch - DELAY * EPOCH_LENGTH
    
    if epoch not in epochs and epoch < earliest_process_epoch:
        print(epoch, earliest_process_epoch)
        raise Exception("skipped epoch")
    if last_commit_epoch > earliest_process_epoch:
        print(epoch)
        print(last_commit_epoch)
        print(earliest_process_epoch)
        raise Exception("insufficient blocks confirmed")

    if epoch in epochs:
        epoch_index = epochs.index(epoch)
        committed_epochs = epochs[epoch_index-2*DELAY:epoch_index-DELAY]
    elif last_commit_epoch in epochs:
        last_index = epochs.index(last_commit_epoch)
        committed_epochs = epochs[last_index - DELAY +1: last_index] + [
            last_commit_epoch
        ]
    else:
        offset = int((current_epoch-epoch) / EPOCH_LENGTH + FORWARD_SLACK_EPOCHS)
        committed_epochs = epochs[-DELAY - offset:]
        committed_epochs = committed_epochs[:DELAY]

    if len(committed_epochs) != DELAY:
        raise Exception('shits fuckd')

    com_hashes = [hashes[epoch] for epoch in committed_epochs]
    commitment = ""
    for com_hash in com_hashes:
        commitment += com_hash
    return commitment.zfill(CHAIN_COMMIT_LEN)
    




