import ast

import config as cfg
import communications as cm
import broadcasts as bc
import peers as pr
import sched, time
from process import Process
from threading import Thread

import hashlib


class VoteProcessor:
    """
    A class used to manage how epoch voting is conducted
    
    Attributes:
    """

    def __init__(self, epoch, seen_bc, execute=True):
        """
        Creates a VoteManager object using the parent Node object

        Most parameters are loaded from the parameter file
        
        Parameters: 
            parent (Node): The node object using this vote manager
        """

        self.epoch = epoch
        self.execute = execute
        self.broadcasts = {bc.calc_bcid(broadcast): broadcast for broadcast in seen_bc}
        self.confs = {
            bc.calc_bcid(broadcast): cfg.VOTE_INIT_CONF for broadcast in seen_bc
        }
        self.count = 0
        self.vote_rounds = 0
        self.s = sched.scheduler(time.time, time.sleep)
        Thread(target=self.execute_vote).start()

    def execute_vote(self):
        if self.execute:
            self.s.enter(cfg.VOTE_ROUND_TIME, 0, self.initiate_vote_update)
            self.s.run()

    def initiate_vote_update(self):
        """
        Initiates a round of voting.

        This function takes a random sample of known peers, opens a voting process,
        and sends vote requests to those peers

        Parameters:
            epoch (int): The epoch of broadcasts to be voted upon
        """
        Process(
            cfg.VOTE_SAMPLE_NUM,
            VoteProcessor.format_vote_response,
            self.conclude_vote_process,
            "vote_request",
            self.epoch,
            True,
        )
        # self.s.enter(cfg.VOTE_ROUND_TIME, 0, self.execute_vote)
        # self.s.run()
        if len(cfg.peers) > 0:
            self.execute_vote()

    def fulfill_vote_request(self, alias: int, request_id: str):
        """
        Fulfills a vote request from a peer for a given epoch

        Parameters:
            alias (int): A valid alias of the peer that sent the request
            request_id (str): The ID of the request that was received
            epoch (int): The epoch of broadcasts to vote on
        """

        if self.execute:
            acks = {bcid for bcid in self.broadcasts if self.confs[bcid] > 0}
            if acks == set():
                acks = {}
            # print("~sending votes",acks)
            commit = hashlib.sha256(
                cfg.chain_commitment(self.epoch).encode("utf-8")
            ).hexdigest()
            cm.send_peer_message(
                alias, f"query_fulfillment|{request_id}|{[acks,commit]}",
            )

    def request_missing_broadcast(self, alias: int, bcid: str):
        """
        Requests the information of a broadcast that the peer knows but the node has not yet seen

        Parameters:
            alias (int): A valid alias of the peer to request the broadcast from
            bcid (str): The ID of the missing broadcast
            epoch (int): The epoch that the missing broadcast belongs to 
        """
        # print("~request missing")
        Process(
            1,
            VoteProcessor.format_bc_response,
            self.conclude_bc_process,
            "bc_request",
            (self.epoch, bcid),
            True,
            specific_peers=[alias],
        )

    def fulfill_bc_request(self, alias: int, query_id: str, bcid: str):
        """
        Fulfills the request from a peer for a specific broadcast

        Parameters:
            alias (int): A valid alias of the peer to send the broadcast to
            query_id (str): The ID of the related query
            bcid (str): The ID of the requested broadcast
            epoch (int): The epoch that the broadcast belongs to 
        """
        broadcast = self.broadcasts[bcid]
        cm.send_peer_message(alias, f"query_fulfillment|{query_id}|{[bcid,broadcast]}")

    @staticmethod
    def format_vote_response(query, response):
        """format recieved string to set"""
        blob = ast.literal_eval(response)
        received_acks = blob[0]
        commit = blob[1]
        if received_acks == {}:
            received_acks = set()
        if type(received_acks) is set:
            return received_acks, commit

    @staticmethod
    def format_bc_response(query, response):
        """format recieved string to list"""
        # print("~format missing resp")
        response = ast.literal_eval(response)
        if type(response) is list:
            return response

    def conclude_bc_process(self, process):
        """incorporate data from missing bc request"""
        # print("~incorporate missing")
        bcid, broadcast = process.cached_responses[0]
        alias = process.specific_peers[0]
        if bcid != bc.calc_bcid(broadcast):
            print("peer send broadcast that didn't match bcid")
            pr.remove_peer(alias)
            return
        if bcid in self.broadcasts:
            # print("~1")
            return
        if not bc.check_broadcast_validity_vote(broadcast, self.epoch):
            # print("~2")
            return
        self.broadcasts[bcid] = broadcast

    def conclude_vote_process(self, process):
        """incorporate information for round of epoch vote"""
        # acks = process.cached_responses
        acks = [i[0] for i in process.cached_responses]
        commits = [i[1] for i in process.cached_responses]
        own_commit = hashlib.sha256(
            cfg.chain_commitment(self.epoch).encode("utf-8")
        ).hexdigest()
        acks = [ack for ack, commit in zip(acks, commits) if commit == own_commit]
        # print(process.cached_responses)
        # print(acks)
        # print(commits)
        # print()

        self.epoch_vote(acks, process)

    def epoch_vote(self, acks, process):
        """
        Updates the confidences for broadcasts based on the votes received by peers

        Parameters:
            acks (list): The responses (votes) of the sampled peers
            vote_process_id (int): The ID of the voting process
        """
        if acks == []:
            return

        acks_union = set.union(*acks)
        acks_union = set.union(acks_union, self.broadcasts)
        # if cfg.current_epoch - self.epoch == 3:
        # print("~union", acks_union)
        # print('~bc', self.confs)
        peers_responded = process.peers_responded
        self.accomodate_missing_bc(acks_union, peers_responded)

        combined_acks = {bcid: 0 for bcid in acks_union}
        for peer_acks in acks:
            for bcid in peer_acks:
                combined_acks[bcid] += 1
        for bcid in combined_acks:
            if combined_acks[bcid] >= cfg.VOTE_CONSENSUS_LEVEL:
                self.confs[bcid] += 1
            elif combined_acks[bcid] <= cfg.VOTE_SAMPLE_NUM - cfg.VOTE_CONSENSUS_LEVEL:
                self.confs[bcid] -= 1
        self.vote_rounds += 1
        # TODO CHECK FOR DRIFT

    def terminate_vote(self):
        """
        Terminates the voting process for the specific epoch

        Parameters:
            epoch (int): The epoch of broadcasts that was voted on
        """

        if self.execute:
            self.execute = False
            return [self.broadcasts[bc] for bc in self.broadcasts if self.confs[bc] > 0]
        return None

    def accomodate_missing_bc(self, acks_union, peers_responeded):
        """
        Updates the set of unconfirmed broadcasts (and confidences) based on differences in the sets of seen broadcasts

        Parameters:
            acks_union (set): The union of the sets of seen broadcasts across the node and its peers
            epoch (int): The epoch that is being voted on (and that the broadcasts belong to)
            acks_individual (list):
            peers_responded (list): The peers that responded in the voting round

        """
        # print('~~',peers_responeded)
        for bcid in acks_union:
            if bcid not in self.broadcasts:
                self.confs[bcid] = cfg.VOTE_INIT_CONF_NEG - self.vote_rounds - 1
                for alias in peers_responeded:
                    if bcid in peers_responeded[alias][0]:
                        self.request_missing_broadcast(alias, bcid)

