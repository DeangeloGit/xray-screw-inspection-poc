"""Reuse byte-identical frame preparation within one immutable detection pair."""
import numpy as np

class PreparedPair:
    def __init__(self):
        self.reference = self.target = self.arrays = None
        self.conversions = 0

    def clear(self):
        self.reference = self.target = self.arrays = None

    def get(self, reference, target):
        # Hold strong references: object IDs alone can be reused by Python.
        # Detector's aligned frames remain immutable while candidates are classified.
        if self.reference is not reference or self.target is not target:
            self.arrays = [(np.clip(im, 0, 1) * 255).astype('uint8').astype('float32') / 255
                           for im in (reference, target)]
            self.reference, self.target = reference, target
            self.conversions += 2
        return self.arrays
