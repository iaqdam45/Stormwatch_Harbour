from simulation import HarbourSim
import sys

def main():
    seed = 11
    policy = 'model'
    use_llm = False
    if len(sys.argv) > 1:
        seed = int(sys.argv[1])
    if len(sys.argv) > 2:
        policy = sys.argv[2]
    if len(sys.argv) > 3:
        use_llm = sys.argv[3].lower() == 'true'

    sim = HarbourSim(seed=seed, policy=policy, use_llm=use_llm)
    res = sim.run()
    print(f"Seed: {seed}, Policy: {policy}, LLM: {use_llm}")
    print(f"Cargo delivered: {res['cargo']}")
    print(f"Storm knockouts: {res['knockouts']}")
    if use_llm:
        print(f"Invalid LLM outputs: {res['invalid_llm']}")
        print(f"Fallback uses: {res['fallback']}")

if __name__ == "__main__":
    main()
