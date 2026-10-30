import random
from collections import deque

# Grid: columns 0-23, rows 0-15
# Berths on north edge (row 0)
BERTHS = {
    'B1': (2, 0),
    'B2': (8, 0),
    'B3': (14, 0),
    'B4': (20, 0)
}
WAREHOUSE = (1, 15)
UNSAFE_BERTHS = {'B1', 'B4'}

class Ship:
    def __init__(self, ship_id, berth, cargo=8):
        self.id = ship_id
        self.berth = berth
        self.cargo = cargo
        self.pos = BERTHS[berth]

class Dockworker:
    def __init__(self, wid, policy='baseline'):
        self.id = wid
        self.pos = (1, 14)  # near warehouse
        self.carrying = 0
        self.target = None
        self.policy = policy
        self.storm_warning = False
        self.warning_ticks = 0

    def move_towards(self, goal):
        x, y = self.pos
        gx, gy = goal
        if x < gx:
            x += 1
        elif x > gx:
            x -= 1
        elif y < gy:
            y += 1
        elif y > gy:
            y -= 1
        self.pos = (x, y)

    def distance(self, goal):
        return abs(self.pos[0] - goal[0]) + abs(self.pos[1] - goal[1])

class Lookout:
    def __init__(self):
        self.storm_active = False
        self.storm_timer = 0
        self.warning_given = False
        self.warning_timer = 0
        self.storms_left = 3
        self.next_storm_tick = None

class HarbourSim:
    def __init__(self, seed=11, policy='baseline', use_llm=False):
        random.seed(seed)
        self.seed = seed
        self.policy = policy
        self.use_llm = use_llm
        self.tick = 0
        self.workers = [Dockworker(i, policy) for i in range(10)]
        self.lookout = Lookout()
        self.ships = []
        self.next_ship_id = 1
        self.free_berths = set(BERTHS.keys())
        self.cargo_delivered = 0
        self.storm_knockouts = 0
        self.invalid_llm = 0
        self.fallback_uses = 0
        self.ship_arrival_interval = random.randint(6, 10)
        self.next_arrival = self.ship_arrival_interval
        # Schedule 3 storms at random times after tick 50
        possible = list(range(80, 550, 40))
        random.shuffle(possible)
        self.storm_starts = sorted(possible[:3])
        self.storm_index = 0

    def schedule_storm(self):
        if self.storm_index < len(self.storm_starts):
            start = self.storm_starts[self.storm_index]
            self.lookout.next_storm_tick = start
            self.storm_index += 1

    def update_lookout(self):
        lo = self.lookout
        if lo.next_storm_tick is None and self.storm_index < 3:
            self.schedule_storm()
        if lo.next_storm_tick is not None:
            ticks_to_storm = lo.next_storm_tick - self.tick
            if ticks_to_storm == 5 and not lo.warning_given:
                lo.warning_given = True
                lo.warning_timer = 5
                for w in self.workers:
                    w.storm_warning = True
                    w.warning_ticks = 5
            if ticks_to_storm <= 0 and not lo.storm_active:
                lo.storm_active = True
                lo.storm_timer = 15
                lo.warning_given = False
                lo.next_storm_tick = None
        if lo.storm_active:
            lo.storm_timer -= 1
            if lo.storm_timer <= 0:
                lo.storm_active = False
                for w in self.workers:
                    w.storm_warning = False

    def arrive_ship(self):
        if self.free_berths and self.tick >= self.next_arrival:
            berth = random.choice(list(self.free_berths))
            self.free_berths.remove(berth)
            ship = Ship(self.next_ship_id, berth)
            self.ships.append(ship)
            self.next_ship_id += 1
            self.ship_arrival_interval = random.randint(6, 10)
            self.next_arrival = self.tick + self.ship_arrival_interval

    def check_knockouts(self):
        if self.lookout.storm_active:
            for ship in list(self.ships):
                if ship.berth in UNSAFE_BERTHS and ship.cargo > 0:
                    # workers at this berth get knocked
                    for w in self.workers:
                        if w.pos == ship.pos and w.carrying == 0:
                            self.storm_knockouts += 1
                            w.pos = (1, 14)  # send back
                            w.target = None

    def get_report(self):
        storm_status = "WARNING" if any(w.storm_warning for w in self.workers) else ("ACTIVE" if self.lookout.storm_active else "NONE")
        berth_status = []
        for b, pos in BERTHS.items():
            status = "free" if b in self.free_berths else "occupied"
            if self.lookout.storm_active and b in UNSAFE_BERTHS:
                status += " (unsafe)"
            berth_status.append(f"{b}:{status}")
        waiting = [s.id for s in self.ships if s.cargo > 0]
        report = f"Storm: {storm_status}. Berths: {', '.join(berth_status)}. Waiting ships: {waiting}"
        return report

    def llm_decide(self, report):
        # Simulated LLM: simple rule based on report
        # In real would call API, here we mock and sometimes give invalid
        if "WARNING" in report or "ACTIVE" in report:
            action = "warn_storm()"
        else:
            waiting = []
            if "Waiting ships:" in report:
                try:
                    part = report.split("Waiting ships: ")[1]
                    waiting = eval(part)  # safe here as we control
                except:
                    waiting = []
            if waiting:
                action = f"hold_ship({waiting[0]})"
            else:
                action = "warn_storm()"
        # Sometimes invalid to test safety
        if random.random() < 0.15:
            action = "release_all_cargo()"  # invalid
        return action

    def validate_action(self, action):
        allowed = ["warn_storm()"]
        if action.startswith("hold_ship(") and action.endswith(")"):
            try:
                sid = int(action[10:-1])
                if any(s.id == sid for s in self.ships):
                    return True, action
            except:
                pass
            return False, None
        if action in allowed:
            return True, action
        return False, None

    def apply_llm_action(self, action):
        if action == "warn_storm()":
            for w in self.workers:
                w.storm_warning = True
                w.warning_ticks = 5
        elif action.startswith("hold_ship("):
            pass  # just acknowledge, no real hold needed for this sim

    def worker_act(self, w):
        # If carrying, go to warehouse
        if w.carrying > 0:
            if w.pos == WAREHOUSE:
                self.cargo_delivered += 1
                w.carrying = 0
                w.target = None
            else:
                w.move_towards(WAREHOUSE)
            return

        # Find ship to collect from
        candidates = [s for s in self.ships if s.cargo > 0]
        if not candidates:
            return

        # Policy decision
        if w.policy == 'model' and w.storm_warning:
            # Avoid unsafe berths
            safe = [s for s in candidates if s.berth not in UNSAFE_BERTHS]
            if safe:
                candidates = safe
            else:
                # wait near warehouse
                if w.pos != (1, 14):
                    w.move_towards((1, 14))
                return

        # Pick closest
        best = min(candidates, key=lambda s: w.distance(s.pos))
        if w.pos == best.pos:
            best.cargo -= 1
            w.carrying = 1
            if best.cargo <= 0:
                self.free_berths.add(best.berth)
                self.ships.remove(best)
        else:
            w.move_towards(best.pos)

    def step(self):
        self.update_lookout()
        self.arrive_ship()
        self.check_knockouts()

        if self.use_llm and self.tick % 20 == 0:
            report = self.get_report()
            raw = self.llm_decide(report)
            valid, action = self.validate_action(raw)
            if valid:
                self.apply_llm_action(action)
            else:
                self.invalid_llm += 1
                self.fallback_uses += 1
                # fallback to model based behaviour already in workers

        for w in self.workers:
            if w.warning_ticks > 0:
                w.warning_ticks -= 1
                if w.warning_ticks == 0:
                    w.storm_warning = False
            self.worker_act(w)

        self.tick += 1

    def run(self, max_ticks=600):
        while self.tick < max_ticks:
            self.step()
        return {
            'cargo': self.cargo_delivered,
            'knockouts': self.storm_knockouts,
            'invalid_llm': self.invalid_llm,
            'fallback': self.fallback_uses
        }


def run_tests():
    results = {}
    for policy in ['baseline', 'model']:
        results[policy] = []
        for seed in [11, 12, 13]:
            sim = HarbourSim(seed=seed, policy=policy)
            res = sim.run()
            results[policy].append(res)
            print(f"{policy} seed {seed}: cargo={res['cargo']} knockouts={res['knockouts']}")
    return results

if __name__ == "__main__":
    run_tests()
