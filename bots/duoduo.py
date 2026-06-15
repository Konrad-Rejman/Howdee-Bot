from phevaluator.evaluator import evaluate_cards
from logic import Move, Player, HandRank
import random

class DuoDuo(Player):
    name = 'Ultra-Adaptive-duoduo'
    image_path = "images/duoduo.png"

    def __init__(self) -> None:
        super().__init__()
        # 对手画像数据
        self.opp_moves = 0
        self.opp_aggressive_moves = 0
        self.last_opp_chips = 10000 # 初始筹码

    def get_equity(self, community_cards: list[str], iterations: int = 400) -> float:
        """强化版蒙特卡洛：更精确的胜率模拟"""
        all_cards = [r+s for r in "23456789TJQKA" for s in "shdc"]
        used_cards = set(community_cards + self.cards)
        deck = [c for c in all_cards if c not in used_cards]
        
        wins = 0
        for _ in range(iterations):
            random.shuffle(deck)
            needed = 5 - len(community_cards)
            sim_community = community_cards + deck[:needed]
            opp_cards = deck[needed:needed+2]
            
            my_score = evaluate_cards(*sim_community, *self.cards)
            opp_score = evaluate_cards(*sim_community, *opp_cards)
            
            if my_score < opp_score: wins += 1
            elif my_score == opp_score: wins += 0.5
        return wins / iterations

    def _get_preflop_strength(self) -> float:
        ranks = "23456789TJQKA"
        r1, r2 = sorted([ranks.index(c[0]) for c in self.cards], reverse=True)
        suited = self.cards[0][1] == self.cards[1][1]
        pair = r1 == r2
        score = r1 * 1.6 + r2
        if pair: score += 22
        if suited: score += 10
        return min(1.0, score / 52.0)

    def move(self, community_cards: list[str], valid_moves: list[Move], round_history: list[tuple[Move, int]], min_bet: int, max_bet: int) -> tuple[Move, int] | Move:
        # --- 1. 对手行为深度学习 ---
        if round_history:
            last_action, amt = round_history[-1]
            if last_action in [Move.BET, Move.RAISE, Move.ALL_IN]:
                self.opp_aggressive_moves += 1
            self.opp_moves += 1

        agg_factor = self.opp_aggressive_moves / self.opp_moves if self.opp_moves > 0 else 0.5
        street = len(community_cards)
        equity = self._get_preflop_strength() if street == 0 else self.get_equity(community_cards)

        # --- 2. 河牌圈诈唬拦截逻辑 (River Bluff Catching) ---
        is_river = (street == 5)
        bluff_catch_mode = False
        
        if is_river and Move.CALL in valid_moves:
            # 计算底池赔率：如果跟注额相对于底池非常大（Overbet），通常随机对手是在诈唬
            # 假设当前需要跟注 min_bet，总筹码 max_bet
            pot_odds = min_bet / (min_bet + max_bet) # 粗略估算
            
            # 如果对手激进且他在河牌推了重注，而我们的胜率尚可（>35%）
            if agg_factor > 0.6 and equity > 0.35:
                bluff_catch_mode = True

        # --- 3. 动态动作执行 ---
        can_raise = Move.RAISE in valid_moves or Move.BET in valid_moves
        can_call = Move.CALL in valid_moves
        can_check = Move.CHECK in valid_moves

        # A. 价值收割 (强牌)
        if equity > 0.8:
            if can_raise:
                # 面对激进对手，直接 All-in 碰运气，他会跟
                if agg_factor > 0.6 and Move.ALL_IN in valid_moves:
                    return Move.ALL_IN
                amount = int(min_bet + (max_bet - min_bet) * 0.7)
                return (Move.RAISE if Move.RAISE in valid_moves else Move.BET, amount)
            return Move.CALL if can_call else Move.CHECK

        # B. 诈唬拦截/中等牌处理
        elif equity > 0.45 or bluff_catch_mode:
            if bluff_catch_mode:
                # 触发拦截：哪怕牌一般，只要对手是疯子且是河牌，就 Call 到底
                return Move.CALL
            
            if can_check:
                # 对付保守对手，在他 Check 后尝试偷底
                if agg_factor < 0.25 and street >= 3 and random.random() < 0.2:
                    if Move.BET in valid_moves:
                        return (Move.BET, min_bet)
                return Move.CHECK
            
            if can_call:
                # 正常情况下，跟注额度不宜超过当前筹码的 1/3
                if min_bet < (max_bet * 0.33):
                    return Move.CALL
            return Move.CHECK if can_check else Move.FOLD

        # C. 弃牌逻辑
        else:
            if can_check:
                return Move.CHECK
            # 面对极小注，还是要看看
            if can_call and min_bet < (max_bet * 0.03):
                return Move.CALL
            return Move.FOLD