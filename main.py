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
MATCHES = 1000
# For development I recommend not processing in parallel as it can make it much harder to find errors
PARALLEL = False

class MyPlayer(Player):
    name = 'Howdee-Bot'
    image_path = 'images/your_image.png' # Optional

    def get_hand_type(self, community_cards: list[str]) -> HandRank:
        # Handle pre flop calls
        if not community_cards:
            return HandRank.ONE_PAIR if self.cards[0][0] == self.cards[1][0] else HandRank.HIGH_CARD

        rank = evaluate_cards(*community_cards, *self.cards)
        for hand_type in HandRank:
            if rank <= hand_type.value:
                return hand_type
        raise IndexError(f'Hand Rank Out Of Range: {rank}')

    def get_equity(self, community_cards: list[str]) -> float:
        """Placeholder equity calculation function. You do not have to implement a function like this but some sort of equity calculation is highly recommended."""

        # Invert rankings
        rankings = {
            1: 7462, # Royal Flush
            10: 6185, # Straight Flush
            166: 3325, # Four of a Kind
            322: 2467, # Full House
            1599: 1609, # Flush
            1609: 1599, # Straight
            2467: 322, # Three of a Kind
            3325: 166, # Two Pair
            6185: 10, # One Pair
            7462: 1 # High Card
        }

        equity = rankings[self.get_hand_type(community_cards)]
        return equity / 7462 # Normalise equity to 0.0 - 1.0

    def move(self, community_cards: list[str], valid_moves: list[Move], round_history: list[tuple[Move, int]], min_bet: int, max_bet: int) -> tuple[Move, int] | Move:
        """Your move code here! You are given the community cards (cards both players have access to, the objective is to use your 2 cards (self.cards) with the community cards to make the best 5-card poker hand).
        You are also given a list containing the legal moves you can currently make, for example, if the opponent has bet then you can only call, raise or fold but cannot check.
        If your bot attempts to make an illegal move it will fold its hand (forfeiting any chips already in the pot), so ensure not to do this."""
        
        # Adjust weights according to hand strength and history

        # Size of pot to bet for
        pot = 0
        for r in round_history:
            pot += r[1]

        # Adjust weights based off hand strength
        equity = self.get_equity(community_cards)

        if equity < 0.33:
            weights = {
                Move.CHECK: 100,
                Move.CALL: 40,
                Move.BET: 5,
                Move.RAISE: 2,
                Move.ALL_IN: 0,
                Move.FOLD: 80
            }

        elif equity < 0.66:
            weights = {
                Move.CHECK: 60,
                Move.CALL: 100,
                Move.BET: 30,
                Move.RAISE: 20,
                Move.ALL_IN: 5,
                Move.FOLD: 20
            }

        else:
            weights = {
                Move.CHECK: 20,
                Move.CALL: 80,
                Move.BET: 80,
                Move.RAISE: 60,
                Move.ALL_IN: 25,
                Move.FOLD: 1
            }

        # Choose random move according to the weights
        weights = [weights[k] for k in valid_moves]
        move = random.choices(valid_moves, weights=weights, k=1)[0]
        if move == Move.RAISE:
            return (Move.RAISE, 100)
        elif move == Move.BET:
            return (Move.BET, min_bet)
        return move

def run_match(_: int) -> str:
    """Run a single match and return the winner's name."""
    p1, p2 = MyPlayer(), RandomPlayer()
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
