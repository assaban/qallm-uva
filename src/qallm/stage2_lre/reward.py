from qallm.stage2_lre.verifier import VerificationResult


class RewardCalculator:
    """Calculates the Quality Delta based on verification results."""

    @staticmethod
    def calculate(result: VerificationResult) -> float:
        if result.is_broken_test:
            return -10.0  # Heavy penalty for unrunnable tests (Self-Correction Trigger)

        reward = 0.0
        # Reward 1: Coverage (0.0 to 1.0)
        reward += (result.coverage / 100.0) * 5.0

        # Reward 2: Finding a bug (The core goal)
        if not result.success and not result.is_broken_test:
            # If the test ran but FAILED, it means it found a bug!
            reward += 10.0

        return reward