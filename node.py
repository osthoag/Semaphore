import os, errno, ast
import config as cfg
import communications as cm
import connections as cn
import consensus as cs
import peers as pr
import clock as cl
import timing as tm
import broadcasts as bc
import reorgs as ro
import time
import json
from alias_management import get_pubkey
from query import Query
from threading import Thread
from sync_processor import InitSyncProcessor


class Node:
    def __init__(self, alias: int, port: int):
        cfg.ALIAS = int(alias)
        cfg.PORT = int(port)

        with open("encrypted&secure_document.txt", "r") as f:
            key_dict = eval(f.read())
        cfg.pk = get_pubkey(cfg.ALIAS)
        cfg.sk = key_dict[cfg.pk]

        cfg.server_socket.bind((cfg.IP, cfg.PORT))
        cfg.server_socket.listen()

        folder = str(cfg.ALIAS)
        if os.path.isdir(folder):
            block_files = [
                file for file in os.listdir(folder) if file.endswith(".json")
            ]
            numbers = [int(name.split(".")[0]) for name in block_files]
            block_files = [file for _, file in sorted(zip(numbers, block_files))]

            for file in block_files:
                name = os.path.join(f"./{folder}", f"{file}")
                with open(name, "rb") as f:
                    block = json.load(f)
                    cs.load_block_data(block)
        else:
            os.mkdir(f"{cfg.ALIAS}")

        t_socket = Thread(target=cm.socket_events, args=[self.interpret_message])
        t_command = Thread(target=self.commands)
        t_timing = Thread(target=tm.time_events)
        t_socket.start()
        t_command.start()
        t_timing.start()

        self.sync = InitSyncProcessor()

    def interpret_message(self, msg: str, alias: int):
        """
        Determines the type of a received message and calls the right function to process it

        Parameters: 
            msg (str): The received message to be interpreted
            alias (int): The alias of the sender
        """
        # Use | as delimeter for message information
        data = msg.split("|")
        # TODO HANDLE SPLITTING MORE ELEGANTLY
        # NOT SURE WHAT CASE THIS IS HANDLING - OSCAR
        if len(data) > 2:
            if data[-2][-1] == "\\":
                join = data[-2] + data[-1]
                data[-2:] = [join]
        msg_type = data[0]

        if msg_type == "chat":
            print(data[1])

        elif msg_type == "time_request":
            query_id = data[1]
            cl.fulfill_time_request(alias, query_id)

        elif msg_type == "vote_request" and cfg.activated:
            query_id = data[1]
            epoch = int(data[2])
            self.execute_process(epoch, "vote", "vote_request", alias, query_id)

        elif msg_type == "query_fulfillment":
            query_id = data[1]
            response = data[2]
            # if 'time_request' in query_id:
            if query_id not in Query.open_queries:
                print(f"{query_id} not in open queries")
                self.peer_manager.remove_peer(
                    alias
                )  # THIS FUNCTION OF REMOVING MISBEHAVING PEERS WAS TAKEN FROM TIMEMANAGER
                return
            Query.open_queries[query_id].process_query_response(response, alias)

        elif msg_type == "bc_request" and cfg.activated:
            query_id = data[1]
            data = ast.literal_eval(data[2])
            epoch, bcid = data
            epoch = int(epoch)
            self.execute_process(epoch, "vote", "bc_request", alias, query_id, bcid)

        elif msg_type == "block_request" and cfg.activated:
            query_id = data[1]
            epoch = int(data[2])
            self.execute_process(epoch, "sync", "block_request", alias, query_id)

        elif msg_type == "history_request":
            query_id = data[1]
            chain_tip_info = ast.literal_eval(data[2])
            chain_tip_epoch, chain_tip_hash = chain_tip_info
            chain_tip_epoch = int(chain_tip_epoch)
            self.sync.fulfill_history_request(alias, query_id, chain_tip_epoch,chain_tip_hash)

        elif msg_type == "fork_request":
            query_id = data[1]
            alt_past_commits = ast.literal_eval(data[2])
            ro.fulfill_fork_request(alias, query_id, alt_past_commits)

        elif msg_type == "relay" and cfg.activated:
            broadcast = data[1]
            bc_data = bc.split_broadcast(broadcast)
            chain_commit = bc_data["chain_commit"]
            # print('~chain commit:',chain_commit)
            if chain_commit in cfg.epoch_chain_commit.keys():
                epoch = cfg.epoch_chain_commit[chain_commit]
                self.execute_process(epoch, "relay", "relay", alias, broadcast)

            else:
                print("~broadcast not in valid epoch")
            # TODO HANDLE ALTERNATE CHAIN

    def execute_process(self, epoch: int, state: str, process: str, alias: int, *args):
        if epoch in cfg.epoch_processes.keys():
            epoch_processor = cfg.epoch_processes[epoch]
            epoch_processor.execute_new_process(state, process, alias, *args)
        else:
            print(
                "~epoch not in keys", alias, process, epoch, cfg.epoch_processes.keys()
            )
            # pr.remove_peer(alias)

    def commands(self):
        """
        Input manual commands when not in testing mode.
        
        The following are the supported commands and arguments.
        
        - connect: Attempts to connect with a specified peer node
        Arguments:
            peer_alias (int): valid alias of a peer to connect to
            peer_ip (str or int): IP address of the peer node
            peer_port (int): device port that the peer is using
        
        - see_peers: Displays all peers connected to the node

        - chat: sends a direct message to a peer with a specified alias
        Arguments:
            alias (int): valid alias of a connected peer
            message (str): message to send to peer. Character limit is ??

        - remove: Removes a connected peer with a specified alias
        Arguments:
            alias (int): valid alias of the peer to be removed

        - exit: Halts the node's processes and exits the Semaphore network

        - epoch: Displays the Semaphore network's current epoch according to the node's time

        - time_synch: Displays the node's network time after sampling peers

        - broadcast: Broadcasts a message to the Semaphore network
        Arguments:
            msg (str): The message to be broadcast. Character limit is ??

        - badcast (str): Creates and distributes an invalid broadcast to test the network
        """
        while True:
            try:
                command = input("command: ")
                if command == "connect":
                    alias = int(input("peer_alias: "))
                    ip = input("peer_ip: ")
                    if "." not in ip:
                        ip = str(cfg.IP)
                    port = input("peer_port: ")
                    try:
                        cn.request_connection(alias, ip, port)
                    except IOError as e:
                        print(e)
                        print("refused")
                        if e.errno == errno.ECONNREFUSED:
                            pass

                elif command == "see_peers":
                    print(cfg.peers.keys())

                elif command == "see_peer_sockets":
                    print(cfg.peer_manager.peers)
                    print(cfg.peer_manager.all_listening)
                    print(cfg.peer_manager.all_speaking)

                elif command == "chat":
                    alias = int(input("alias: "))
                    msg = input("message: ")
                    cm.send_peer_chat(alias, msg)

                elif command == "remove":
                    alias = int(input("alias: "))
                    pr.remove_peer(alias)

                elif command == "exit":
                    os._exit(0)

                elif command == "time_sync":
                    cl.initiate_time_update()
                    time.sleep(0.1)
                    print(cfg.network_time())
                elif command == "activate":
                    if not cfg.activated:
                        tm.activate()
                    else:
                        print("already activated")
                elif command == "deactivate":
                    if  cfg.activated:
                        tm.deactivate()
                    else:
                        print("not activated")
                elif command == "sync":
                    if not cfg.activated:
                        self.sync = InitSyncProcessor()
                    else:
                        print("already activated")

                elif command == "get_alt":
                    alias = int(input("peer_alias: "))
                    ro.request_fork_history(alias)
                elif (
                    command == "badcast"
                ):  # SEND MESSAGE WITH BAD SIGNATURE FOR TESTING
                    timestamp = self.time_event_manager.epoch
                    broadcast = self.broadcast_manager.generate_broadcast(
                        f"{self.ALIAS}badcast", timestamp, ""
                    )
                    if self.ALIAS != 0:
                        broadcast = broadcast[:128] + "0000000000" + broadcast[138:]
                    else:
                        broadcast = broadcast[:128] + "0000000001" + broadcast[138:]
                    timestamps = self.time_event_manager.timestamps
                    if timestamp in timestamps:
                        self.relay_manager.unconf_bc[timestamps[timestamp]].add(
                            broadcast
                        )
                    self.peer_manager.gossip_msg(f"relay|{broadcast}")

            except EOFError:
                os._exit(0)


if __name__ == "__main__":
    # b = Node(1, 2346)
    b = Node(input("alias: "), input("port: "))
