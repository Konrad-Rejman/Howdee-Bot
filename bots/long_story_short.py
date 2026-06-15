# Your code here
from phevaluator.evaluator import evaluate_cards
from logic import Move, Game, Player, HandRank, RockyPlayer, RandomPlayer
from collections import Counter
from multiprocessing import Pool, cpu_count
import random

# Feel free to set a seed for testing, otherwise leave commmented out to test your bot in a variety of random spots
# Note that you cannot set a seed and run the simulation in parallel
# random.seed(6767)

# How many heads up matches you want to simulate
MATCHES = 20000
# For development I recommend not processing in parallel as it can make it much harder to find errors
PARALLEL = True


class LSS_ItsOver(Player):
    name = 'Long Story Short, Its over'
    image_path = 'images/LongStoryShort.png' # Optional

    def __init__(self):
        super().__init__()
        self._is_button = False

    def get_opponent_tendency(self) -> str:
        # Not enough data yet, assume unknown
        if len(self.hands_shown) < 6:
            return 'unknown'
        
        # Count how often they show up with strong hands at showdown
        strong = sum(1 for _, rank in self.hands_shown
                    if rank in (
                        HandRank.TWO_PAIR,
                        HandRank.THREE_OF_A_KIND,
                        HandRank.STRAIGHT,
                        HandRank.FLUSH,
                        HandRank.FULL_HOUSE,
                        HandRank.FOUR_OF_A_KIND,
                        HandRank.STRAIGHT_FLUSH,
                        HandRank.ROYAL_FLUSH
                    ))
        ratio = strong / len(self.hands_shown)
        
        if ratio > 0.5:
            return 'tight'   # only goes to showdown with strong hands
        elif ratio < 0.3:
            return 'loose'   # goes to showdown with weak hands often
        else:
            return 'neutral'

    def preflop_strength(self) -> float:
        ranks = '23456789TJQKA'
        r1, r2 = self.cards[0][0], self.cards[1][0]
        s1, s2 = self.cards[0][1], self.cards[1][1]
        v1 = ranks.index(r1)
        v2 = ranks.index(r2)
        is_pair = r1 == r2
        is_suited = s1 == s2
        high = max(v1, v2)
        low = min(v1, v2)
        gap = high - low
        score = (high + low) / 24.0
        if is_pair:
            score += 0.3 + (high / 12.0) * 0.2
        if is_suited:
            score += 0.06
        if gap <= 2 and not is_pair:
            score += 0.05
        return min(score, 1.0)
    
    def get_equity(self, community_cards: list[str], samples: int = 200) -> float:
        """Placeholder equity calculation function. You do not have to implement a function like this but some sort of equity calculation is highly recommended."""
        known = set(self.cards + community_cards)
        deck = [r + s for r in '23456789TJQKA' for s in 'dhsc' if r + s not in known]
        wins = 0
        my_rank = evaluate_cards(*community_cards, *self.cards)
        for i in range(samples):
            opp_cards = random.sample(deck, 2)
            opp_rank = evaluate_cards(*community_cards, *opp_cards)
            if my_rank <= opp_rank:
                wins += 1
        return wins / samples

    def get_hand_type(self, community_cards: list[str]) -> HandRank:
        # Handle pre flop calls
        if not community_cards:
            return HandRank.ONE_PAIR if self.cards[0][0] == self.cards[1][0] else HandRank.HIGH_CARD

        rank = evaluate_cards(*community_cards, *self.cards)
        for hand_type in HandRank:
            if rank <= hand_type.value:
                return hand_type
        raise IndexError(f'Hand Rank Out Of Range: {rank}')

    
    def move(self, community_cards: list[str], valid_moves: list[Move], round_history: list[tuple[Move, int]], min_bet: int, max_bet: int) -> tuple[Move, int] | Move:
        """Your move code here! You are given the community cards (cards both players have access to, the objective is to use your 2 cards (self.cards) with the community cards to make the best 5-card poker hand).
        You are also given a list containing the legal moves you can currently make, for example, if the opponent has bet then you can only call, raise or fold but cannot check.
        If your bot attempts to make an illegal move it will fold its hand (forfeiting any chips already in the pot), so ensure not to do this."""
        is_preflop = len(community_cards) == 0

        if is_preflop:
            strength = self.preflop_strength()
        else:
            strength = self.get_equity(community_cards)

        tendency = self.get_opponent_tendency()

        stack_ratio = self.chips / 10000  # 1.0 = starting stack, >1.0 = winning, <1.0 = losing

        # Position detection
        is_button = len(round_history) == 2 and is_preflop
        if is_preflop:
            self._is_button = is_button

        # Call cost and big bet detection
        call_cost = 0
        aggressive = [amt for move, amt in round_history if move in (Move.BET, Move.RAISE, Move.ALL_IN)]
        if aggressive:
            call_cost = aggressive[-1] - self.pot_commitment
        facing_big_bet = call_cost > self.chips * 0.2

        #If loosing be aggresive boi with a good strenght percentage
        if stack_ratio < 0.4 and strength > 0.60:
            if Move.ALL_IN in valid_moves:
                return Move.ALL_IN
            
        #if preflop is dodo water then fold or check
        if is_preflop and strength < 0.35:
            if Move.FOLD in valid_moves:
                return Move.FOLD
            if Move.CHECK in valid_moves:
                return Move.CHECK

        #VERY STRONG HAND GOES BRRRR
        if strength > 0.90 and not is_preflop:
            if Move.ALL_IN in valid_moves:
                return Move.ALL_IN
            if Move.RAISE in valid_moves:
                return (Move.RAISE, max_bet)
            if Move.BET in valid_moves:
                return (Move.BET, max_bet)
            if Move.CALL in valid_moves:
                return Move.CALL
            return Move.FOLD
        
        # STRONG
        elif strength > 0.75:
            if facing_big_bet:
                if Move.RAISE in valid_moves:
                    return (Move.RAISE, min(max_bet, min_bet * 3))
                if Move.CALL in valid_moves:
                    return Move.CALL
                return Move.ALL_IN
            bet_size = min(max_bet, int(self.chips * 0.24))
            if Move.RAISE in valid_moves:
                return (Move.RAISE, min(max_bet, min_bet * 3))
            if Move.BET in valid_moves:
                return (Move.BET, max(min_bet, bet_size))
            if Move.CALL in valid_moves:
                return Move.CALL
            return Move.ALL_IN

        # MEDIUM
        elif strength > 0.50:
            if facing_big_bet:
                my_contribution = self.pot_commitment
                opp_contribution = aggressive[-1] if aggressive else 0
                pot_size = my_contribution + opp_contribution + call_cost
                pot_odds = call_cost / pot_size if pot_size > 0 else 1.0

                # Adjust call threshold based on opponent tendency
                if tendency == 'loose':
                    call_threshold = pot_odds * 0.85  # call wider against loose players
                elif tendency == 'tight':
                    call_threshold = pot_odds * 1.15  # fold more against tight players
                else:
                    call_threshold = pot_odds  # neutral/unknown, use raw pot odds

                if strength > call_threshold:
                    if Move.CALL in valid_moves:
                        return Move.CALL
                    if Move.ALL_IN in valid_moves:
                        return Move.ALL_IN
                if Move.CHECK in valid_moves:
                    return Move.CHECK
                return Move.FOLD

            # On button post-flop with medium hand, bet to apply pressure
            if self._is_button and not is_preflop:
                if Move.BET in valid_moves:
                    return (Move.BET, min(max_bet, 200))
            if Move.CHECK in valid_moves:
                return Move.CHECK
            if Move.CALL in valid_moves:
                call_amount = aggressive[-1] - self.pot_commitment if aggressive else 0
                stack_threshold = 0.25 if stack_ratio < 0.8 else 0.20
                if call_amount < self.chips * stack_threshold and strength > 0.52:
                    return Move.CALL
            return Move.FOLD
        # WEAK
        else:
            should_bluff = (tendency in ('loose', 'unknown') or stack_ratio < 0.7)
            if should_bluff and not facing_big_bet:
                if Move.BET in valid_moves:
                    bluff_size = 200 if tendency == 'loose' else 150
                    return (Move.BET, min(max_bet, bluff_size))
            if Move.CHECK in valid_moves:
                return Move.CHECK
            return Move.FOLD


def run_match(_: int) -> str:
    """Run a single match and return the winner's name."""
    p1, p2 = LSS_ItsOver(), RandomPlayer()
    game = Game(p1, p2, debug=False)
    return game.simulate_hands().name

if __name__ == '__main__':
    win_counts = Counter()
    # This runs the large number of matches in parallel, which drastically speeds up computation time
    if (PARALLEL):
        with Pool(cpu_count()) as pool:
            results = pool.map(run_match, range(MATCHES))
            win_counts.update(results)
    else:
        for i in range(MATCHES):
            win_counts.update((run_match(i),)) 

    player_name, wins = win_counts.most_common(1)[0]
    print(f'{player_name} won the most with {wins}/{MATCHES} ({(wins / MATCHES) * 100:.2f}%)')