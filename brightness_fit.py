"""Byte-preserving scratch-buffer implementation of the three exposure-fit rounds."""
import cv2
import numpy as np

def brightness(ref, target):
    # Keep the original dtype promotion and operation order, including rounding.
    # Reuse scratch buffers; the last round's weights have no subsequent reader.
    weights = np.ones_like(ref, dtype=np.float32)
    wr, tmp, tmp2 = (np.empty_like(ref) for _ in range(3))
    def average(a):
        return cv2.boxFilter(a, -1, (101, 101), normalize=True, borderType=cv2.BORDER_REFLECT)
    for round_index in range(3):
        mass = average(weights); np.maximum(mass, .01, out=mass)
        np.multiply(weights, ref, out=wr)
        mean_ref = average(wr); np.divide(mean_ref, mass, out=mean_ref)
        np.multiply(weights, target, out=tmp)
        mean_target = average(tmp); np.divide(mean_target, mass, out=mean_target)
        np.multiply(wr, ref, out=tmp)
        variance = average(tmp); np.divide(variance, mass, out=variance)
        np.square(mean_ref, out=tmp); np.subtract(variance, tmp, out=variance)
        np.maximum(variance, 0, out=variance)
        np.multiply(wr, target, out=tmp)
        covariance = average(tmp); np.divide(covariance, mass, out=covariance)
        np.multiply(mean_ref, mean_target, out=tmp); np.subtract(covariance, tmp, out=covariance)
        # Short row strips keep consecutive arithmetic near one another in memory.
        predicted = np.empty_like(ref)
        if round_index == 0:
            # Input images can be float64; the original first reweight promotes
            # the initial float32 weights to the predicted image's dtype.
            weights = np.empty_like(predicted)
        for top in range(0, ref.shape[0], 64):
            sl = slice(top, top+64)
            a, b = tmp[sl], tmp2[sl]
            np.add(covariance[sl], .002, out=a); np.add(variance[sl], .002, out=b)
            np.divide(a,b,out=a); np.clip(a,.6,1.6,out=a)  # gain
            np.multiply(a,mean_ref[sl],out=b); np.subtract(mean_target[sl],b,out=b)
            np.clip(b,-.25,.25,out=b)  # offset
            np.multiply(a,ref[sl],out=a); np.add(a,b,out=predicted[sl])
            np.clip(predicted[sl],0,1,out=predicted[sl])
            if round_index < 2:
                np.subtract(predicted[sl],target[sl],out=a); np.abs(a,out=a)
                np.maximum(a,.0001,out=a); np.divide(.04,a,out=a)
                np.minimum(1,a,out=a); np.square(a,out=weights[sl])
    return predicted
