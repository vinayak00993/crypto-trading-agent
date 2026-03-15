import sys

path = "src/agent/strategies/ml_meta_learner.py"
lines = open(path).readlines()

# Fix lines 138-144 (index 137-143)
lines[137] = "    def save_training_data(self, samples: list[dict]) -> None:\n"
lines[138] = '        path = self.data_dir / "training_samples.json"\n'
lines[139] = "        # Keep last 5000 samples\n"
lines[140] = "        samples = samples[-5000:]\n"
lines[141] = '        with open(path, "w") as f:\n'
lines[142] = "            json.dump(samples, f, default=str)\n"
lines[143] = '            log.debug("ml.memory_saved", samples=len(samples), path=str(path))\n'

open(path, "w").writelines(lines)
print("Fixed!")
