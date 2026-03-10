# Main file containing the backend/game logic
#! DO NOT EDIT THE CONTENTS OF THIS FILE, YOUR SUBMISSION WILL BE VOIDED
from __future__ import annotations # Handles typing errors on earlier versions of Python
from abc import abstractmethod
from typing import Generator
from phevaluator.evaluator import evaluate_cards
from enum import Enum, IntEnum
import random

# The bot that busts (runs out of chips) first loses, or, after MAX_HANDS the bot with more chips wins
MAX_HANDS = 10000
STARTING_STACK = 10000

class HandRank(IntEnum):
    """Hand rankings where lower values indicate stronger hands.
    Values represent the upper bound rank for each hand type."""
    ROYAL_FLUSH = 1
    STRAIGHT_FLUSH = 10
    FOUR_OF_A_KIND = 166
    FULL_HOUSE = 322
    FLUSH = 1599
    STRAIGHT = 1609
    THREE_OF_A_KIND = 2467
    TWO_PAIR = 3325
    ONE_PAIR = 6185
    HIGH_CARD = 7462

    @property
    def display_name(self) -> str:
        """Returns "Royal Flush" etc"""
        return self.name.replace('_', ' ').title()

def get_hand_type(rank: int) -> HandRank:
    for hand_type in HandRank:
        if rank <= hand_type.value:
            return hand_type
    raise IndexError(f'Hand Rank Out Of Range: {rank}')

class Move(Enum):
    """Contains the different legal poker moves (Check, Call, Bet, Raise, All-in, and Fold)."""
    CHECK = 1
    CALL = 2
    BET = 3
    RAISE = 4
    FOLD = 5
    ALL_IN = 6

class Deck:
    def __init__(self, cards: list[str] | None=None) -> None:
        self.cards: list[str] = cards if cards is not None else []
        self.ranks = ('2','3','4','5','6','7','8','9','T','J','Q','K','A')
        if self.cards: return
        # Represents cards in standard Poker notation, i.e., Td3s is the Ten of Diamonds and the Three of Spades.
        for suit in ('d','h','s','c'):
            for rank in self.ranks:
                self.cards.append(rank + suit)

    def shuffles_generator(self) -> Generator[tuple[int, Deck]]:
        for i in range(MAX_HANDS):
            random.shuffle(self.cards)
            yield (i, Deck(self.cards.copy()))

    def deal(self, n: int) -> list[str]:
        """Deals the top n cards from the deck. Deals the cards in reverse rank order (i.e., AhKh and not KhAh). Errors if there are not enough cards left."""
        if n > (n_cards := len(self.cards)):
            raise IndexError(f'Requested {n} cards but there are only {n_cards} left in the deck.')
        dealt_cards = self.cards[:n]
        self.cards = self.cards[n:]

        dealt_cards.sort(reverse=True, key=lambda card: self.ranks.index(card[0]))
        return dealt_cards

class Game:
    """Main game class which handles the simulation of poker between the two bots."""
    def __init__(self, player1: Player, player2: Player, debug: bool = False) -> None:
        self.deck = Deck()

        self.players = (player1, player2)
        # The button determines the order in which players can take action and dictates the blind paid, starting pos of the button is random for consistency
        self.button = random.choice((0, 1))
        # The small/big blind levels. This level dictates that each player starts with 100BBs (Big Blinds) based on a 10,000 chip starting stack, which is standard
        self.blinds = (50, 100)
        # Resets at the start of each hand
        self.pot = 0

        self.debug = debug

    def simulate_hands(self) -> Player:
        """Simulates the number of hands specified by SHUFFLES."""
        for hand_number, deck in self.deck.shuffles_generator():
            # The game is over, one of the bots has won
            if self.players[0].chips == 0 or self.players[1].chips == 0:
                if self.debug: print(f'{self.players[0].name if self.players[1].chips == 0 else self.players[1].name} has won the game after {hand_number} hands!')
                return self.players[0] if self.players[1].chips == 0 else self.players[1]
            
            button_player, bb_player = self.players[self.button], self.players[(self.button + 1) % 2]

            community_cards: list[str] = []
            self.pot = 0
            # Deal the players 2 cards each
            bb_player.set_cards(deck.deal(2))
            button_player.set_cards(deck.deal(2))
            p1pos, p2pos = ('D', 'BB') if self.players[0] == button_player else ('BB', 'D')
            if self.debug:
                print(f'\n---------------------- Hand Number: {hand_number + 1} ---------------------- \
                      \n{self.players[0].name}\'s ({p1pos}) Chips: {self.players[0].chips}, Cards: {self.players[0].cards} \
                      \n{self.players[1].name}\'s ({p2pos}) Chips: {self.players[1].chips}, Cards: {self.players[1].cards}')

            # Run Pre-Flop, Flop, Turn and River
            player_folds = self.betting_streets(community_cards, deck)
            if player_folds:
                self.button = (self.button + 1) % 2 
                continue

            # Showdown - If both players got to this point without a fold etc then best hand wins
            p1hand, p2hand = evaluate_cards(*community_cards, *self.players[0].cards), evaluate_cards(*community_cards, *self.players[1].cards)
            p1hand_enum, p2hand_enum = get_hand_type(p1hand), get_hand_type(p2hand)
            self.players[0].hands_shown.append((self.players[1].cards.copy(), p2hand_enum))
            self.players[1].hands_shown.append((self.players[0].cards.copy(), p1hand_enum))
            # Split pot (they both have the same hand)
            if p1hand == p2hand:
                # The player most out of position (big blind) gets the extra chip if the pot is not splittable equally
                half, remainder = divmod(self.pot, 2)
                button_player.chips += half
                bb_player.chips += half + remainder
                if self.debug: print(f'The hand was a draw, both players had {p1hand_enum.display_name}')
            else:
                self.players[0 if p1hand < p2hand else 1].chips += self.pot
                if self.debug:
                    print(f'{self.players[0].name} won the hand with a {p1hand_enum.display_name}, while player 2 had a {p2hand_enum.display_name}.' if p1hand < p2hand else \
                        f'{self.players[1].name} won the hand with a {p2hand_enum.display_name}, while player 1 had a {p1hand_enum.display_name}.')
            # End of round, move dealer button
            self.button = (self.button + 1) % 2

        # No player has bust, the one with more chips wins
        return self.players[0] if self.players[0].chips > self.players[1].chips else self.players[1]

    def sanity_check(self, community_cards: list[str], deck: Deck) -> None:
        """Simple checks to see if something has gone wrong such as a bot trying to change its own cards, give itself chips etc"""
        if self.players[0].chips + self.players[1].chips + self.pot != STARTING_STACK * 2:
            raise Exception('Chip count mismatch!')

        cards: set[str] = {*deck.cards, *community_cards, *self.players[0].cards, *self.players[1].cards}
        if len(cards) != 52:
            raise Exception('Deck modification detected!')

    def betting_streets(self, community_cards: list[str], deck: Deck) -> bool:
        """Runs Pre-Flop, Flop, Turn and River streets for the bots"""
        # Pre-Flop
        player_folds = self.betting_phase(community_cards, self.button, preflop=True)
        if player_folds: return True
        # Flop, Turn and River
        for name, n_cards in (('Flop', 3), ('Turn', 1), ('River', 1)):
            community_cards += deck.deal(n_cards)
            if self.debug: print(f'\n{name}: {community_cards}')
            # Run sanity check after each betting phase to ensure everything is still in order
            self.sanity_check(community_cards, deck)
            player_folds = self.betting_phase(community_cards, (self.button + 1) % 2)
            if player_folds: return True

        return False
    
    def betting_phase(self, community_cards: list[str], current_action: int, preflop = False) -> bool:
        """Run a betting round."""
        actions_remaining = 2
        betting_history = []

        current_player, opponent = self.players[current_action], self.players[(current_action + 1) % 2]
        current_player.pot_commitment, opponent.pot_commitment = 0, 0
        # The players are forced to bet the small and big blinds before action continues at the start of any hand (pre-flop, i.e., before any community cards are drawn)
        if preflop:
            # If the player cannot cover a blind, they are forced all-in
            small_blind = min(self.blinds[0], current_player.chips)
            self.handle_bet(current_action, small_blind)
            betting_history.append((Move.BET, small_blind))

            big_blind = min(self.blinds[1], self.players[(current_action + 1) % 2].chips)
            self.handle_bet((current_action + 1) % 2, big_blind)
            betting_history.append((Move.BET, big_blind))

        # No more action if one player is all in
        if self.players[0].chips == 0 or self.players[1].chips == 0:
            # Refund excess commitment when one player is all in from a blind but can't the full blind
            if preflop:
                smaller = min(current_player.pot_commitment, opponent.pot_commitment)
                for p in (current_player, opponent):
                    excess = p.pot_commitment - smaller
                    if excess > 0:
                        p.chips += excess
                        self.pot -= excess
            return False

        # Keep getting player action until there is no action left
        while actions_remaining > 0:
            valid_moves = []
            min_bet = self.calculate_min_bet(preflop, betting_history)
            max_bet = current_player.chips + current_player.pot_commitment
            # A raise has to be by at least the amount of the previous raise (e.g., p1 bets 100, p2 raises to 200, min raise is now 300)
            if betting_history:
                match betting_history[-1][0]:
                    case Move.CHECK:
                        valid_moves += [Move.CHECK, Move.BET, Move.ALL_IN]
                    case Move.CALL:
                        # Check is included here because the only case where there is still action after the opponent calls is pre-flop 
                        # where the small blind calls and the big blind gets option
                        valid_moves += [Move.CHECK, Move.RAISE, Move.ALL_IN]
                    # If the other player is all in we can only fold, call, or go all in ourselves (if we have less chips)
                    case Move.ALL_IN:
                        if max_bet > (opponent_max := opponent.chips + opponent.pot_commitment):
                            valid_moves += [Move.FOLD, Move.CALL]
                            max_bet = opponent_max
                        else:
                            valid_moves += [Move.FOLD, Move.ALL_IN]
                    case Move.BET | Move.RAISE:
                        valid_moves += [Move.FOLD, Move.CALL, Move.ALL_IN]
                        if max_bet > min_bet:
                            valid_moves += [Move.RAISE]
            else:
                valid_moves += [Move.CHECK, Move.BET, Move.ALL_IN]

            move = self.get_player_move(current_action, community_cards, valid_moves, betting_history, min_bet, max_bet)
            # The round is over
            if move == Move.FOLD: return True

            # Aggressive action reopens betting for the other players
            if actions_remaining > 1 or move not in (Move.BET, Move.RAISE, Move.ALL_IN):
                actions_remaining -= 1

            # This player moved all in to cover the raise from the other player, the original raiser gets refunded any extra chips on top of the all in and action has concluded
            if move == Move.ALL_IN and opponent.pot_commitment >= max_bet:
                refund = opponent.pot_commitment - max_bet
                self.pot -= refund
                opponent.chips += refund
                break

            # Move the action on
            current_action = (current_action + 1) % 2
            current_player, opponent = self.players[current_action], self.players[(current_action + 1) % 2]
        return False

    def calculate_min_bet(self, preflop: bool, betting_history: list[tuple[Move, int]]) -> int:
        aggressive_history = [x for x in betting_history if x[0] in {Move.ALL_IN, Move.BET, Move.RAISE}]

        if not aggressive_history:
            return self.blinds[1]
        
        if preflop and len(aggressive_history) <= 2:
            # Only blinds so far, min raise = 2BB
            return self.blinds[1] * 2

        last_bet = aggressive_history[-1][1]
        prev_bet = aggressive_history[-2][1] if len(aggressive_history) >= 2 else 0
        raise_increment = max(abs(last_bet - prev_bet), self.blinds[1])
        return last_bet + raise_increment

    def get_player_move(self, current_action: int, community_cards: list[str], valid_moves: list[Move], betting_history: list[tuple[Move, int]], min_bet: int, max_bet: int) -> Move:
        # Default values for if the move function returns something random
        move, amount = Move.FOLD, 0
        # Accounts for moves which require a chip value to be specified compared to moves where the chip value does not need to be specified
        match self.players[current_action].move(community_cards.copy(), valid_moves.copy(), betting_history.copy(), min_bet, max_bet):
            case Move() as m, int() as n:
                move, amount = m, n
            case Move() as m:
                move = m
            case _:
                # The bot must've returned something invalid, automatically fold them
                move = Move.FOLD
        # Invalid move returned by bot, penalise
        if move not in valid_moves:
            if self.debug: print(f'{self.players[current_action].name} made an invalid move {move}, forcing a fold.')
            move = Move.FOLD

        match move:
            case Move.CHECK:
                # Checking requires no further action as there is no change to the chip state
                pass
            case Move.CALL:
                amount = betting_history[-1][1]
                if amount > max_bet:
                    amount = max_bet
                    move = Move.ALL_IN
                self.handle_bet(current_action, amount)
            case Move.BET | Move.RAISE:
                # Player tried betting/raising more chips than they have, they are forced all in
                amount = max(min_bet, amount)
                if amount > max_bet:
                    amount = max_bet
                    move = Move.ALL_IN
                self.handle_bet(current_action, amount)
            case Move.FOLD:
                # The other player automatically wins the hand
                self.players[(current_action + 1) % 2].chips += self.pot
            case Move.ALL_IN:
                amount = max_bet
                self.handle_bet(current_action, amount)

        if self.debug:
            print(f'Min bet/raise is: {min_bet}, Max bet for {self.players[current_action].name} is {max_bet}.')
            print(f'{self.players[current_action].name} does move {move}', f'for {amount} chips ({amount / self.blinds[1]}BB)' if amount > 0 else '')
        betting_history.append((move, amount))

        return move

    def handle_bet(self, current_action: int, total_commitment: int) -> None:
        """Set a player's total pot commitment for this street to `total_commitment`."""
        current_player = self.players[current_action]
        incremental = total_commitment - current_player.pot_commitment
        assert incremental >= 0, f'Player {current_player} is trying to commit negative chips to the pot'
        current_player.pot_commitment = total_commitment
        current_player.chips -= incremental
        self.pot += incremental

class Player:
    name = 'John/Jane Doe'

    def __init__(self) -> None:
        # Default is 10,000 starting stack, you can modify the starting stacks for testing how your bot might perform short stacked but make sure not to submit it with this
        self.chips = STARTING_STACK
        # Will track chips put into a pot on a given street (i.e., if you already have 500 chips in the pot and get raised to 2000, the value of this variable will be 500)
        self.pot_commitment = 0
        # Tracks the hands the opponent has shown at showdown along with its value, e.g., (['As', 'Ks'], HandRank.ROYAL_FLUSH)
        self.hands_shown: list[tuple[list[str], HandRank]] = []

    def set_cards(self, cards: list[str]) -> None:
        self.cards = cards

    @abstractmethod
    def move(self, community_cards: list[str], valid_moves: list[Move], round_history: list[tuple[Move, int]], min_bet: int, max_bet: int) -> tuple[Move, int] | Move:
        ...

class RockyPlayer(Player):
    """This player is extremely scared and only plays the best of the best (known as the Rock player type), this is not a good strategy and is extremely exploitable. 
    Your bot should always win against this player type overall."""
    name = 'Rocky'    

    def move(self, community_cards: list[str], valid_moves: list[Move], round_history: list[tuple[Move, int]], min_bet: int, max_bet: int) -> tuple[Move, int] | Move:
        """Makes a rocky move."""
        playable_hands = {'AA', 'KK', 'QQ', 'JJ'}
        # Extremely passive
        if Move.CHECK in valid_moves:
            return Move.CHECK

        if self.cards[0][0] + self.cards[1][0] in playable_hands:
            if Move.CALL in valid_moves:
                return (Move.CALL, round_history[-1][1])
            else:
                return Move.ALL_IN
        # Folds to any aggression if the bot doesn't have a "playable hand" (don't use this strategy!)
        return Move.FOLD

class RandomPlayer(Player):
    """This player is unpredicatable and completely random (an extreme version of the Maniac player type), this is another terrible strategy.
    Your bot should always win against this player type overall."""
    name = 'Rando'

    def move(self, community_cards: list[str], valid_moves: list[Move], round_history: list[tuple[Move, int]], min_bet: int, max_bet: int) -> tuple[Move, int] | Move:
        """Makes a random move."""
        move = random.choice(valid_moves)
        amount = 0
        if move in (Move.BET, Move.RAISE):
            if min_bet >= self.chips:
                return Move.ALL_IN
            amount = random.randint(min_bet, self.chips)

        if move in (Move.BET, Move.RAISE):
            return (move, amount)
        else:
            return move
