# Your code here
from phevaluator.evaluator import evaluate_cards
from logic import Move, Game, Player, HandRank, RockyPlayer, RandomPlayer
from collections import Counter
from multiprocessing import Pool, cpu_count
import random
import math

# Feel free to set a seed for testing, otherwise leave commmented out to test your bot in a variety of random spots
# Note that you cannot set a seed and run the simulation in parallel
# random.seed(6767)

# How many heads up matches you want to simulate
MATCHES = 100
# For development I recommend not processing in parallel as it can make it much harder to find errors
PARALLEL = True

# https://gist.github.com/laundmo/b224b1f4c8ef6ca5fe47e132c8deab56
def lerp(a: float, b: float, t: float) -> float:
    return (1 - t) * a + t * b
    
def saturate(v):
    return max(0.0, min(1.0, v))
    

class CraAAcked(Player):
    name = "CrAAcked (ALL-IN)"
    image_path = "images/craacked.jpg"  # Optional

    def __init__(self):
        super().__init__() # ong we all sliming ethan 
        self.PreFlopActionhistory = []
        self.OpALLINCallRate = 0
        self.opponent_aggression = 0.5
        self.average_opponent_aggression = (
            0.5  # 1 = maximally aggressive, 0.5 = minimally aggressive
        )
        self.hands_played = 0
        self.hands = 0
        self.UltraPremiums = [
            "AA", "KK", "QQ", "JJ", "TT",
            "AK", "AQ", "AJ", "AT"
        ]


        self.premiums = [
            # Strong pairs
            "99", "88", "77", "66",

            # Strong Ax
            "A9", "A8", "A7", "A6", "A5",

            # Broadways
            "KQ", "KJ", "KT",
            "QJ", "QT",
            "JT", "T9",

            # Medium pairs
            "55", "44", "33", "22"
        ]

    
        self.Playable = [
            # Remaining Ax
            "A4", "A3", "A2",

            # Kx
            "K9", "K8", "K7", "K6", "K5", "K4", "K3",

            # Qx
            "Q9", "Q8"
        ]
    
        self.weak = [
            # Kx
            "K2",

            # Qx
            "Q7", "Q6", "Q5", "Q4", "Q3", "Q2",

            # Jx
            "J9", "J8", "J7", "J6", "J5", "J4", "J3", "J2",

            # Tx
            "T8", "T7", "T6", "T5", "T4", "T3", "T2",

            # 9x
            "98", "97", "96", "95", "94", "93", "92",

            # 8x
            "87", "86", "85", "84", "83", "82",

            # 7x
            "76", "75", "74", "73", "72",

            # 6x
            "65", "64", "63", "62",

            # 5x
            "54", "53", "52",

            # 4x
            "43", "42",

            # 3x / 2x
            "32"
        ]


    def get_hand_type(self, community_cards: list[str]) -> HandRank:
        # Handle pre flop calls
        if not community_cards:
            return (
                HandRank.ONE_PAIR
                if self.cards[0][0] == self.cards[1][0]
                else HandRank.HIGH_CARD
            )
        rank = evaluate_cards(*community_cards, *self.cards)
        for hand_type in HandRank:
            if rank <= hand_type.value:
                return hand_type
        raise IndexError(f"Hand Rank Out Of Range: {rank}")
    
    def get_hand_type_test(self, hole_cards, community_cards: list[str]) -> HandRank:
        # Handle pre flop calls
        if not community_cards:
            return (
                HandRank.ONE_PAIR
                if hole_cards[0][0] == hole_cards[1][0]
                else HandRank.HIGH_CARD
            )

        rank = evaluate_cards(*community_cards, *hole_cards)
        for hand_type in HandRank:
            if rank <= hand_type.value:
                return hand_type
        raise IndexError(f"Hand Rank Out Of Range: {rank}")
    
    def get_high_card(self):
        ranks = ['2','3','4','5','6','7','8','9','T','J','Q','K','A']
        c1 = self.cards[0][0]
        c2 = self.cards[1][0]
        if ranks.index(c1) > ranks.index(c2):
            return c1
        else:
            return c2

    def get_equity(self, community_cards: list[str], samples: int = 5000) -> float:
        """Placeholder equity calculation function. You do not have to implement a function like this but some sort of equity calculation is highly recommended."""
        ranks = ['2','3','4','5','6','7','8','9','T','J','Q','K','A']
        suits = ['s','h','d','c']

        ownHandType = self.get_hand_type(community_cards)

        winNum = 0
        chopNum = 0
        lossNum = 0
        total = 0

        for rank1 in ranks:
            for suit1 in suits:
                for rank2 in ranks:
                    for suit2 in suits:
                        if rank1+suit1 != rank2+suit2 and rank1+suit1 not in community_cards and rank2+suit2 not in community_cards:
                            handType = self.get_hand_type_test([rank1+suit1,rank2+suit2],community_cards)
                            if ownHandType < handType:
                                winNum += 1
                            elif ownHandType > handType:
                                lossNum += 1
                            else:

                                chopNum += 1
                            total += 1

        return((winNum + chopNum/2)/total)

    def get_pot(self, round_history):
        if round_history == []:
            return 0
        if len(round_history) == 1:
            return round_history[0][1]
        return round_history[-1][1] + round_history[-2][1]

    def aggression_heuristic(self,bet, min_bet):
        if bet < min_bet:
            return 0.0

        # between 1 and 3xbig blind interpolate to 0.5
        if bet < min_bet * 3:
            return lerp(min_bet, min_bet * 3, bet) * 0.5

        return saturate(lerp(min_bet * 3, min_bet * 6, bet))
    
    def get_bet_amount(self,current_opponent_aggression, average_opponent_aggression, equity, min_bet):
        aggression_ratio = current_opponent_aggression / average_opponent_aggression
        aggression_ratio = saturate(lerp(0, 2, aggression_ratio))
        
        bet_amount = aggression_ratio * (1.0 - equity)
        if bet_amount < 0.25:
            return 0
        bet_amount = saturate(lerp(0.25, 0.75, bet_amount))
        bet_amount = bet_amount * min_bet * 5 + min_bet
        return bet_amount
        
    def move(self, community_cards: list[str], valid_moves: list[Move], round_history: list[tuple[Move, int]], min_bet: int, max_bet: int,) -> tuple[Move, int] | Move:
        """Your move code here! You are given the community cards (cards both players have access to, the objective is to use your 2 cards (self.cards) with the community cards to make the best 5-card poker hand).
        You are also given a list containing the legal moves you can currently make, for example, if the opponent has bet then you can only call, raise or fold but cannot check.
        If your bot attempts to make an illegal move it will fold its hand (forfeiting any chips already in the pot), so ensure not to do this.
        """

        # calculate aggression of opponent move, update average aggression
        if len(round_history) > 0:
            self.opponent_aggression *= math.ceil(len(round_history) / 2) - 1
            self.opponent_aggression += self.aggression_heuristic(
                round_history[-1][1] or 0, min_bet
            )
            self.opponent_aggression /= math.ceil(len(round_history) / 2)
        
        

        return Move.ALL_IN
    
    def SBPostFlopAction(self, round_history, min_bet, community_cards, valid_moves):
        OpAction, OPAmount = round_history[-1]
        equity = self.get_equity(community_cards)
        self.get_bet_amount(self.opponent_aggression, self.average_opponent_aggression, equity, min_bet)
        if OpAction == Move.RAISE and OPAmount >= 3*min_bet:
            if equity > 0.6:
                return Move.RAISE, 3*min_bet
        elif OpAction == Move.RAISE:
            if equity > 0.5:
                return Move.RAISE, min_bet
            if equity > 0.3:
                return Move.CALL
        elif OpAction == Move.CHECK:
            if equity >= 0.2:
                return Move.BET, min_bet
            return Move.CHECK

    def BBPostFlopAction(self, round_history, min_bet, community_cards, valid_moves):
        equity = self.get_equity(community_cards)
        if equity < 0.2:
            return Move.CHECK
        if 0.4 < equity < 0.6:
            return Move.BET, min_bet * (1+(1-self.average_opponent_aggression))
        if 0.6 < equity < 0.8:
            return Move.BET, min_bet * (3+(1-self.average_opponent_aggression))
        if equity > 0.8:
            return Move.BET, min_bet * (6+(1-self.average_opponent_aggression))

    def BBpreFlopAction(self, key, suited, raiseAmount, round_history, valid_moves):
        if round_history[-1][0] == Move.ALL_IN:
            if key in self.UltraPremiums:
                return Move.ALL_IN
            
        if round_history[-1][0] == Move.RAISE and round_history[-1][1] >= 3*raiseAmount:
            if key in self.UltraPremiums:
                return Move.RAISE, 5*raiseAmount
            if key in self.premiums:
                return Move.RAISE, 2*raiseAmount
            else:
                return Move.FOLD
            
        if round_history[-1][0] == Move.RAISE:
            if key in self.UltraPremiums:
                return Move.RAISE, 3*raiseAmount
            if key in self.premiums:
                return Move.RAISE, raiseAmount
            if key in self.Playable:
                return Move.CALL
            
        if round_history[-1][0] == Move.CALL:
            if key in self.UltraPremiums:
                return Move.BET, 2*raiseAmount
            if key in self.premiums:
                return Move.BET, raiseAmount
            return Move.CHECK
            
        return Move.CHECK
    
    def SBpreFlopAction(self, key, raiseAmount, suited):
        if key in self.UltraPremiums:
            return Move.RAISE, 4*raiseAmount
        if key in self.premiums:
            return Move.RAISE, 2*raiseAmount
        if key in self.Playable and suited:
            return Move.RAISE, raiseAmount
        if key in self.Playable and not suited:
            return Move.CALL
        if key in self.weak:
            return Move.FOLD

    def key(self):
        key = self.cards[0][0] + self.cards[1][0]
        if self.cards[0][:-1] == self.cards[1][:-1]:
            suited = True
        else:
            suited = False
        return key, suited
    


class CraAAcked_REAL(Player):
    name = "CrAAcked (REAL)"
    image_path = "images/your_image.png"  # Optional

    def __init__(self):
        super().__init__() # ong we all sliming ethan 
        self.PreFlopActionhistory = []

        self.opponent_aggression = 0.5
        self.average_opponent_aggression = (
            0.5  # 1 = maximally aggressive, 0.5 = minimally aggressive
        )
        self.hands_played = 0

        self.UltraPremiums = [
        "AA", "KK", "QQ", "JJ", "TT",
        "AK", "AQ", "AJ", "AT"
        ]

        self.premiums = [
            # Strong pairs
            "99", "88", "77", "66",

            # Strong Ax
            "A9", "A8", "A7", "A6", "A5",

            # Broadways
            "KQ", "KJ", "KT",
            "QJ", "QT",
            "JT", "T9",

            # Medium pairs
            "55", "44", "33", "22"
        ]
    
        self.Playable = [
            # Remaining Ax
            "A4", "A3", "A2",

            # Kx
            "K9", "K8", "K7", "K6", "K5", "K4", "K3",

            # Qx
            "Q9", "Q8", "Q7", "Q6", "Q5", "Q4",

            # Jx
            "J9", "J8", "J7", "J6", "J5",

            # Tx
            "T8", "T7", "T6", "T5"

            # 9x
            "98", "97", "96",

            # 8x
            "87", "86",

            # 7x
            "76", "75",

            # 6x
            "65", "64"

            # 5x
            "54",

            # 4x
            "43"
            ]
    
        self.weak = [
            "K2",
            "Q3", "Q2",
            "J4", "J3", "J2",
            "T4", "T3", "T2", 
            "95", "94", "93", "92", 
            "85", "84", "83", "82", 
            "74", "73", "72", 
            "63", "62", 
            "53", "52", 
            "42", 
            "32"
        ]

    def get_hand_type(self, community_cards: list[str]) -> HandRank:
        # Handle pre flop calls
        if not community_cards:
            return (
                HandRank.ONE_PAIR
                if self.cards[0][0] == self.cards[1][0]
                else HandRank.HIGH_CARD
            )

        rank = evaluate_cards(*community_cards, *self.cards)
        for hand_type in HandRank:
            if rank <= hand_type.value:
                return hand_type
        raise IndexError(f"Hand Rank Out Of Range: {rank}")
    
    def get_hand_type_test(self, hole_cards, community_cards: list[str]) -> HandRank:
        # Handle pre flop calls
        if not community_cards:
            return (
                HandRank.ONE_PAIR
                if hole_cards[0][0] == hole_cards[1][0]
                else HandRank.HIGH_CARD
            )

        rank = evaluate_cards(*community_cards, *hole_cards)
        for hand_type in HandRank:
            if rank <= hand_type.value:
                return hand_type
        raise IndexError(f"Hand Rank Out Of Range: {rank}")
    
    def get_high_card(self):
        ranks = ['2','3','4','5','6','7','8','9','T','J','Q','K','A']
        c1 = self.cards[0][0]
        c2 = self.cards[1][0]
        if ranks.index(c1) > ranks.index(c2):
            return c1
        else:
            return c2
    
    def get_equity(self, community_cards: list[str], samples: int = 5000) -> float:
        """Placeholder equity calculation function. You do not have to implement a function like this but some sort of equity calculation is highly recommended."""
        ranks = ['2','3','4','5','6','7','8','9','T','J','Q','K','A']
        suits = ['s','h','d','c']

        ownHandType = self.get_hand_type(community_cards)

        winNum = 0
        chopNum = 0
        lossNum = 0

        total = 0

        for rank1 in ranks:
            for suit1 in suits:
                for rank2 in ranks:
                    for suit2 in suits:
                        if rank1+suit1 != rank2+suit2 and rank1+suit1 not in community_cards and rank2+suit2 not in community_cards:
                            handType = self.get_hand_type_test([rank1+suit1,rank2+suit2],community_cards)
                            if ownHandType < handType:
                                winNum += 1
                            elif ownHandType > handType:
                                lossNum += 1
                            else:

                                chopNum += 1
                            total += 1

        return((winNum + chopNum/2)/total)

    def get_pot(self, round_history):
        if round_history == []:
            return 0
        if len(round_history) == 1:
            return round_history[0][1]
        return round_history[-1][1] + round_history[-2][1]
        
    def move(self, community_cards: list[str], valid_moves: list[Move], round_history: list[tuple[Move, int]], min_bet: int, max_bet: int,) -> tuple[Move, int] | Move:
        """Your move code here! You are given the community cards (cards both players have access to, the objective is to use your 2 cards (self.cards) with the community cards to make the best 5-card poker hand).
        You are also given a list containing the legal moves you can currently make, for example, if the opponent has bet then you can only call, raise or fold but cannot check.
        If your bot attempts to make an illegal move it will fold its hand (forfeiting any chips already in the pot), so ensure not to do this.
        """

        Action = Move.FOLD

        key, suited = self.key()
        
        if len(community_cards) == 0:
            if len(round_history) == 3:
                Action = self.BBpreFlopAction(key, suited, min_bet, round_history, valid_moves)
            elif len(round_history) == 2:
                Action = self.SBpreFlopAction(key, min_bet, suited)
            else:
                Action = self.BBPostFlopAction(round_history, min_bet, community_cards, valid_moves)
        elif len(community_cards) >= 3:
            if len(round_history) == 0:
                Action = self.BBPostFlopAction(round_history, min_bet, community_cards, valid_moves)
            else:
                Action = self.SBPostFlopAction(round_history, min_bet, community_cards, valid_moves)


        return Action
    
    def SBPostFlopAction(self, round_history, min_bet, community_cards, valid_moves):
        OpAction, OPAmount = round_history[-1]
        equity = self.get_equity(community_cards)
        if OpAction == Move.RAISE and OPAmount >= 3*min_bet:
            if equity > 0.8:
                return Move.RAISE, 3*min_bet
        elif OpAction == Move.RAISE:
            if equity > 0.65:
                return Move.RAISE, min_bet
            if equity > 0.5:
                return Move.CALL
        elif OpAction == Move.CHECK:
            if equity >= 0.5:
                return Move.BET, min_bet
            return Move.CHECK

    def BBPostFlopAction(self, round_history, min_bet, community_cards, valid_moves):
        equity = self.get_equity(community_cards)
        if equity < 0.4:
            return Move.CHECK
        if 0.4 < equity < 0.6:
            return Move.BET, min_bet * (1+(1-self.average_opponent_aggression))
        if 0.6 < equity < 0.8:
            return Move.BET, min_bet * (3+(1-self.average_opponent_aggression))
        if equity > 0.8:
            return Move.BET, min_bet * (6+(1-self.average_opponent_aggression))

    def BBpreFlopAction(self, key, suited, raiseAmount, round_history, valid_moves):
        if round_history[-1][0] == Move.ALL_IN:
            if key in self.UltraPremiums:
                return Move.ALL_IN
            
        if round_history[-1][0] == Move.RAISE and round_history[-1][1] >= 3*raiseAmount:
            if key in self.UltraPremiums:
                return Move.RAISE, 5*raiseAmount
            if key in self.premiums:
                return Move.RAISE, 2*raiseAmount
            else:
                return Move.FOLD
            
        if round_history[-1][0] == Move.RAISE:
            if key in self.UltraPremiums:
                return Move.RAISE, 3*raiseAmount
            if key in self.premiums:
                return Move.RAISE, raiseAmount
            if key in self.Playable:
                return Move.CALL
            
        if round_history[-1][0] == Move.CALL:
            if key in self.UltraPremiums:
                return Move.BET, 2*raiseAmount
            if key in self.premiums:
                return Move.BET, raiseAmount
            return Move.CHECK
            
        return Move.CHECK
    
    def SBpreFlopAction(self, key, raiseAmount, suited):
        if key in self.UltraPremiums:
            return Move.RAISE, 4*raiseAmount
        if key in self.premiums:
            return Move.RAISE, 2*raiseAmount
        if key in self.Playable and suited:
            return Move.RAISE, raiseAmount
        if key in self.Playable and not suited:
            return Move.CALL
        if key in self.weak:
            return Move.FOLD

    def key(self):
        key = self.cards[0][0] + self.cards[1][0]
        if self.cards[0][:-1] == self.cards[1][:-1]:
            suited = True
        else:
            suited = False
        return key, suited

def run_match(_: int) -> str:
    """Run a single match and return the winner's name."""
    p1, p2 = CraAAcked(), RandomPlayer()
    game = Game(p1, p2, debug=False)
    return game.simulate_hands().name


if __name__ == "__main__":
    win_counts = Counter()
    # This runs the large number of matches in parallel, which drastically speeds up computation time
    if PARALLEL:
        with Pool(cpu_count()) as pool:
            results = pool.map(run_match, range(MATCHES))
            win_counts.update(results)
    else:
        for i in range(MATCHES):
            win_counts.update((run_match(i),))

    player_name, wins = win_counts.most_common(1)[0]
    print(
        f"{player_name} won the most with {wins}/{MATCHES} ({(wins / MATCHES) * 100:.2f}%)"
    )
