import verde as vd
from scipy.spatial import KDTree
import numpy as np

def _interpolate(interp_method, fromx, fromy, data, tox, toy, k):
    # interpolate
    if interp_method == 'spline':
        interp = vd.Spline()
    elif interp_method == 'linear':
        interp = vd.Linear()
    elif interp_method == 'kneighbors':
        interp = vd.KNeighbors(k=k)
    else:
        raise ValueError('the interp_method is not correctly defined, exit the function')
    
    interp.fit((fromx, fromy), data)
    result = interp.predict((tox, toy))
    
    return result

def min_dist_from_mask(xx, yy, mask):
    """
    Distance from every grid node to the nearest cell where ``mask`` is true.

    ``xx`` and ``yy`` are the 2-D coordinate grids. The result has the same
    shape and is in the same units as those coordinates (meters on the
    Stancomb-Wills grid). ``get_crf_weight`` and ``get_edge_masks`` turn this
    distance into the logistic conditioning weight. No random numbers are used.
    """
    tree = KDTree(np.array([xx[mask], yy[mask]]).T)
    distance = tree.query(np.array([xx.ravel(), yy.ravel()]).T)[0].reshape(xx.shape)
    return distance