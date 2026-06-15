from phevaluator.evaluator import evaluate_cards
from logic import Move, Game, Player, HandRank, RandomPlayer, RockyPlayer
from collections import Counter
from multiprocessing import Pool, cpu_count
import random

MATCHES = 1000
PARALLEL = True

class Jokers(Player):
    name = 'THÊ Jokêrs'
    image_path = 'images/Joker.png'
    
    #2 , 3, 4, 5, 6,7,8,9,T(Ten),J(Jack),Q(Queen),K(King),A(Ace)
    _FULL_DECK = [r + s for r in '23456789TJQKA' for s in 'cdhs']
    _RANK_ORDER = '23456789TJQKA'

    def __init__(self):
        super().__init__()
        self.hands_played = 0
        self._cache = {}
        # Track opponent folding to detect if they CAN fold
        self.opp_bets_faced = 0
        self.opp_folds = 0
        self.can_opponent_fold = None  # Unknown initially

    def _pot_size(self, round_history):
        return max(1, sum(amount for _, amount in round_history))

    def _to_call(self, round_history):
        if not round_history:
            return 0
        move, amount = round_history[-1]
        return amount if move in (Move.BET, Move.RAISE, Move.ALL_IN) else 0


    #Determines what round of the game you are in
    def _street(self, community_cards):
        n = len(community_cards)
        return 0 if n == 0 else 1 if n == 3 else 2 if n == 4 else 3

    #Hand evaluation against the board
    def _hand_key(self, cards):
        r1, r2 = sorted([self._RANK_ORDER.index(c[0]) for c in cards], reverse=True)
        suited = cards[0][1] == cards[1][1]
        return self._RANK_ORDER[r1] + self._RANK_ORDER[r2] + ('s' if suited else 'o')

    # ============ FAST EVALUATION ============

    def _preflop_equity_fast(self):
        """Fast preflop equity estimation"""
        r1, r2 = sorted([self._RANK_ORDER.index(c[0]) for c in self.cards], reverse=True)
        suited = self.cards[0][1] == self.cards[1][1]
        
        base = 0.35 + (r1 + r2) / 50.0
        if suited:
            base += 0.03
        if r1 == r2:
            base += 0.15
        return min(0.60, base)

    def _hand_rank_fast(self, community_cards, hole_cards):
        all_cards = list(community_cards) + list(hole_cards)
        return evaluate_cards(*all_cards)

    def _hand_strength_fast(self, community_cards):
        """0-100 score"""
        if not community_cards:
            return int(self._preflop_equity_fast() * 100)
        
        rank = self._hand_rank_fast(community_cards, self.cards)
        
        # Convert to 0-100 scale
        if rank <= 10:      return 100  # Royal/Straight flush
        elif rank <= 166:   return 95   # Quads
        elif rank <= 322:   return 90   # Full house
        elif rank <= 1600:  return 85   # Flush
        elif rank <= 1609:  return 80   # Straight
        elif rank <= 2468:  return 75   # Trips
        elif rank <= 3326:  return 70   # Two pair
        elif rank <= 6186:  return 55   # One pair
        else:
            # High card
            board_ranks = [self._RANK_ORDER.index(c[0]) for c in community_cards]
            my_ranks = [self._RANK_ORDER.index(c[0]) for c in self.cards]
            top_board = max(board_ranks) if board_ranks else 0
            overs = sum(1 for r in my_ranks if r > top_board)
            return 20 + overs * 10

    # ============ OPPONENT FOLD DETECTION ============

    def _track_opponent_action(self, round_history):
        """Simple tracking: does opponent ever fold?"""
        if len(round_history) < 2:
            return
        
        # Look at opponent's last action
        last_move, _ = round_history[-1]
        
        # If we bet and they folded
        if len(round_history) >= 2:
            prev_move, _ = round_history[-2]
            if prev_move in (Move.BET, Move.RAISE) and last_move == Move.FOLD:
                self.opp_folds += 1
            if prev_move in (Move.BET, Move.RAISE):
                self.opp_bets_faced += 1

    def _opponent_can_fold(self):
        """Determine if opponent is capable of folding"""
        if self.can_opponent_fold is not None:
            return self.can_opponent_fold
            
        if self.opp_bets_faced < 3:
            return None  # Unknown
        
        fold_rate = self.opp_folds / self.opp_bets_faced
        # If they fold more than 25% of the time, they CAN fold
        self.can_opponent_fold = fold_rate > 0.25
        return self.can_opponent_fold

    # ============ BLUFFING LOGIC ============

    def _should_bluff(self, community_cards, street, round_history):
        """
        PURE BLUFF: Betting with complete air (high card only, no draw)
        Only do this against opponents who CAN fold
        """
        # Never bluff random players
        can_fold = self._opponent_can_fold()
        if can_fold is False:
            return False, 0
        
        # Only bluff on flop/turn (not river - too risky)
        if street >= 3:
            return False, 0
        
        # Need complete air (high card only, strength < 30)
        strength = self._hand_strength_fast(community_cards)
        if strength >= 30:
            return False, 0  # We have something, not a pure bluff
        
        # Board texture check - don't bluff into scary boards
        board_ranks = [self._RANK_ORDER.index(c[0]) for c in community_cards]
        
        # Don't bluff if board has obvious draws that hit their range
        # (simplified: don't bluff paired or coordinated boards)
        if len(set(board_ranks)) < len(board_ranks):  # Paired board
            return False, 0
        
        # Calculate bluff size (smaller = less risk)
        pot = self._pot_size(round_history)
        bluff_size = int(pot * 0.33)  # Small bluff
        
        # Frequency: bluff 20% of spots against folder, 0% vs random
        if can_fold is True and random.random() < 0.2:
            return True, bluff_size
        
        return False, 0

    def _semi_bluff(self, community_cards, street, round_history, min_bet, max_bet):
        """
        SEMI-BLUFF: Betting with draws (we have equity if called)
        This is profitable even vs calling stations
        """
        strength = self._hand_strength_fast(community_cards)
        
        # Semi-bluff: weak made hand + draw potential (strength 35-60)
        if not (35 <= strength < 60):
            return None
        
        # Only on flop/turn
        if street >= 3:
            return None
        
        # Bet size for semi-bluff
        pot = self._pot_size(round_history)
        bet = int(pot * 0.5)
        bet = min(max_bet, max(min_bet, bet))
        
        return bet

    # ============ MAIN DECISION ============

    def move(self, community_cards, valid_moves, round_history, min_bet, max_bet):
        # Clear cache on new hand
        if not community_cards and not round_history:
            self.hands_played += 1
            if self.hands_played % 10 == 0:
                self._cache.clear()
            # Reset fold detection every few hands to adapt
            if self.hands_played % 50 == 0:
                self.can_opponent_fold = None

        # Track opponent
        self._track_opponent_action(round_history)

        street = self._street(community_cards)
        to_call = self._to_call(round_history)
        pot = self._pot_size(round_history)
        strength = self._hand_strength_fast(community_cards)
        
        # Estimate equity
        if not community_cards:
            equity = self._preflop_equity_fast()
        else:
            # Fast postflop equity estimate based on hand type
            equity = strength / 100.0
        
        pot_odds = to_call / (pot + to_call) if to_call > 0 else 0

        # === FACING ALL-IN ===
        if to_call >= self.chips * 0.9:
            if equity > 0.52:
                return Move.ALL_IN if Move.ALL_IN in valid_moves else (Move.CALL if Move.CALL in valid_moves else Move.FOLD)
            return Move.FOLD

        # === PREFLOP ===
        if street == 0:
            if to_call == 0:
                if equity > 0.50:
                    bet = min(max_bet, max(min_bet, int(pot * 2.5)))
                    if Move.BET in valid_moves:
                        return Move.BET, bet
                    if Move.RAISE in valid_moves:
                        return Move.RAISE, bet
                return Move.CHECK if Move.CHECK in valid_moves else Move.FOLD
            
            if equity > pot_odds + 0.05:
                if Move.CALL in valid_moves:
                    return Move.CALL
            return Move.FOLD

        # === POSTFLOP: NO BET TO FACE ===
        if to_call == 0:
            # 1. Value bet strong hands
            if strength >= 70:
                bet = min(max_bet, max(min_bet, int(pot * 0.75)))
                if Move.BET in valid_moves:
                    return Move.BET, bet
            
            # 2. Semi-bluff draws (profitable even vs random)
            semi_bet = self._semi_bluff(community_cards, street, round_history, min_bet, max_bet)
            if semi_bet and Move.BET in valid_moves:
                return Move.BET, semi_bet
            
            # 3. PURE BLUFF (only vs folders)
            should_bluff, bluff_amount = self._should_bluff(community_cards, street, round_history)
            if should_bluff and bluff_amount > 0:
                if Move.BET in valid_moves:
                    return Move.BET, bluff_amount
            
            return Move.CHECK if Move.CHECK in valid_moves else Move.FOLD

        # === POSTFLOP: FACING BET ===
        if to_call > 0:
            # Large bet: need decent hand
            if to_call > pot * 0.5:
                if strength >= 50 or equity > 0.45:
                    return Move.CALL if Move.CALL in valid_moves else Move.FOLD
                return Move.FOLD
            
            # Small bet: call wide
            if strength >= 30 or equity > pot_odds:
                return Move.CALL if Move.CALL in valid_moves else Move.FOLD
            
            return Move.FOLD

        return Move.FOLD


def run_match(_):
    p1, p2 = Jokers(), RandomPlayer()
    game = Game(p1, p2, debug=False)
    return game.simulate_hands().name


if __name__ == '__main__':
    win_counts = Counter()
    print(f'Starting tournament: {MATCHES} matches\n')

    if PARALLEL:
        with Pool(cpu_count()) as pool:
            for i, result in enumerate(pool.imap_unordered(run_match, range(MATCHES)), start=1):
                win_counts.update((result,))
                if i % 100 == 0:
                    print(f'Completed: {i}/{MATCHES}')
    else:
        for i in range(MATCHES):
            win_counts.update((run_match(i),))
            if (i + 1) % 100 == 0:
                print(f'Completed: {i + 1}/{MATCHES}')

    for name, wins in win_counts.most_common():
        print(f'\n{name}: {wins}/{MATCHES} ({(wins / MATCHES) * 100:.2f}%)')