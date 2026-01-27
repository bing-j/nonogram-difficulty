import itertools, random, json

IDS = list(range(6))
SEED = 42  # fixed for reproducibility

# 1) all ordered triples of 3 distinct puzzles: 6P3 = 120
all_triples = list(itertools.permutations(IDS, 3))

# 2) group by first element
groups = {i: [] for i in IDS}
for t in all_triples:
    groups[t[0]].append(list(t))

# 3) optional shuffle within each first-id group (keeps your [0,...], [1,...] pattern)
rng = random.Random(SEED)
for i in IDS:
    rng.shuffle(groups[i])

# 4) round-robin interleave: [0,...], [1,...], ... [5,...], then repeat
schedule = []
while any(groups[i] for i in IDS):
    for i in IDS:
        if groups[i]:
            schedule.append(groups[i].pop())

assert len(schedule) == 120

# save as JSON you can commit
with open("../assignment_schedule_6puzzles_3perms.json", "w", encoding="utf-8") as f:
    json.dump({"version": 1, "sequences": schedule}, f, indent=2)
