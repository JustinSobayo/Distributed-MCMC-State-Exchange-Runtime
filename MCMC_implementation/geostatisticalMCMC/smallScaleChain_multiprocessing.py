import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from gstatsMCMC import Topography
from gstatsMCMC import MCMC
import gstatsim as gs
from sklearn.preprocessing import QuantileTransformer
import skgstat as skg
from copy import deepcopy
import time
import multiprocessing as mp
from pathlib import Path
import os
import sys
import scipy as sp
import json
import psutil

def largeScaleChain_mp(n_chains,n_workers,largeScaleChain,rf,initial_beds,rng_seeds,n_iters,output_path='./Data/output'):
    '''
    function to run multiple large scale chain using multiprocessing

    Parameters
    ----------
    n_chains (int): the number of chains this multiprocessing choose to run
    n_workers (int): the number of processes the multiprocessing function create. Must be less than the number of CPUs you have
    largeScaleChain (MCMC.chain_crf): an existing large scale chain that has already been set-up
    rf (MCMC.RandField): an existing RandField instance that has already been set-up
    initial_beds (list): a list of subglacial topography (each of which are a 2D numpy array) used to initialize each chain
    rng_seeds (list): a list of int used to initialize the random number generator of each chain
    n_iters (int): a list of number of iterations runned for each chain
    output_path (str): Path to the folder where the user wants to save results

    Returns
    -------
    result: a list of results from all the chains runned.

    '''
    # Clear the console for the progress bars
    os.system('cls' if os.name == 'nt' else 'clear')
    
    tic = time.time()
    
    params = []

    # Retrive parameters from the existing chain / RandField
    example_chain = largeScaleChain.__dict__ 
    example_RF = rf.__dict__

   # Modify some of the parameters based on the input rng_seeds, initial_beds, and n_iters
    for i in range(n_chains):   
        chain_param = deepcopy(example_chain)
        chain_param['rng_seed'] = rng_seeds[i]
        chain_param['initial_bed'] = initial_beds[i]
        
        RF_param = deepcopy(example_RF)
        RF_param['rng_seed'] = rng_seeds[i]

        run_param = {} # A dictionary of parameters passed in the run() function
        run_param['n_iter'] = n_iters[i]
        run_param['only_save_last_bed']=True # Some display parameters are fixed.
        run_param['info_per_iter']=1000
        run_param['plot']=False
        run_param['progress_bar']=False
        run_param['chain_id'] = i
        run_param['tqdm_position'] = i + 1 # 1 extra line for header
        run_param['seed'] = rng_seeds[i]
        run_param['output_path'] = str(Path(output_path) / 'LargeScaleChain')

        params.append([chain_param,RF_param,deepcopy(run_param)])

    # Print header and reserve space for progress bars
    print('Running MCMC chains...')
    print('\n' * (n_chains + 1))
    sys.stdout.flush() # Force output into the terminal
    
    # The multiprocessing step
    with mp.Pool(n_workers) as pool:
        result = pool.starmap(lsc_run_wrapper, params)


    print('\n')
    print(r'''
           _o                  _                 _o_   o   o
      o    (^)  _             (o)    >')         (^)  (^) (^)
   _ (^) ('>~ _(v)_      _   //-\\   /V\      ('> ~ __.~   ~
 ('v')~ // \\  /-\      (.)-=_\_/)   (_)>     (V)  ~  ~~ /__ /\
//-=-\\ (\_/) (\_/)      V \ _)>~    ~~      <(__\[     ](__=_')
(\_=_/)  ^ ^   ^ ^       ~  ~~                ~~~~        ~~~~~
_^^_^^   __  ..-.___..---I~~~:_  .__...--.._.;-'I~~~~-.____...;-
 |~|~~~~~| ~~|  _   |    |  _| ~~|  |  |  |  |_ |      | _ |  |
_.-~~_.-~-~._.-~~._.-~-~_.-~~_.-~~_.-~-~._.-~~._.-~-~_.-~~_.-~-~
    ''')

    toc = time.time()
    print(f'Completed in {toc-tic:.2f} seconds')
    
    return result

def lsc_run_wrapper(param_chain, param_rf, param_run):
    '''
    A function used to initialize chain by input parameters and run the chains

    Parameters
    ----------
    param_chain (dict): Dictionary containing parameters needed to initialize chain
    param_rf (dict): Dictionary containing parameters needed to initialize random field
    param_run (dict): Dictionary containing parameters needed to run chain

    Returns
    -------
    result (tuple): A tuple containing the results of the run

    '''

    # Suppress initialization prints from workers
    old_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')

    chain = MCMC.init_lsc_chain_by_instance(param_chain)
    rf1 = MCMC.initiate_RF_by_instance(param_rf)

    # Restore stdout after initialization
    sys.stdout.close()
    sys.stdout = old_stdout

    # Setup output path
    output_path = param_run.get('output_path', './Data/LargeScaleChain')
    seed = param_run['seed']
    n_iter = param_run['n_iter']
    seed_folder = Path(output_path) / f'{str(seed)[:6]}'

    # Check for existing bed files (to resume progress)
    # existing_beds = list(seed_folder.glob('bed_*.txt'))
    exist_chain = list(seed_folder.glob('current_iter.txt'))
    cumulative_iters = 0
    previous_results = None
    files_to_delete = []

    # Prepare to merge/concatenate existing files with new results
    #if existing_beds:
    if exist_chain:
        #bed_file = existing_beds[0] # Existing bed file
        
        # Extract iteration count from filename
        #filename = bed_file.stem  # Gets 'bed_100k' from 'bed_100k.txt'
        #iter_str = filename.split('_')[1].replace('k', '')  # Gets '100' from 'bed_100k'
        #iter_count = int(iter_str)
        #cumulative_iters = iter_count * 1000  # Convert back to actual iterations
        cumulative_iters = int(np.loadtxt(exist_chain[0]))
        iter_count = int(cumulative_iters / 1000)
        bed_file = 'bed_'+str(iter_count)+'k.txt'
        
        # Load the most recent bed file
        most_recent_bed = np.load(seed_folder / f'bed_{iter_count}k.npy')
        
        # Update the chain's initial bed
        chain.initial_bed = most_recent_bed
        
        # Load all previous result files
        with np.load(seed_folder / f'results_{iter_count}k.npz') as results_data:
            previous_results = {
                'loss_mc' : results_data['loss_mc'].copy(),
                'loss_data' : results_data['loss_data'].copy(),
                'loss' : results_data['loss'].copy(),
                'steps' : results_data['steps'].copy(),
                'resampled_times' : results_data['resampled_times'].copy(),
                'blocks_used' : results_data['blocks_used'].copy()
            }
        
        # Mark files for deletion
        files_to_delete = [
            seed_folder / f'results_{iter_count}k.npz',
            seed_folder / 'current_iter.txt'
        ]
        
        with open(seed_folder / 'RNGState_RandField.txt', "r") as file: 
            rf1.rng.bit_generator.state = json.load(file)
        with open(seed_folder / 'RNGState_chain.txt', "r") as file: 
            chain.rng.bit_generator.state = json.load(file)

    # Store positioning info
    chain.chain_id = param_run.get('chain_id', 'Unknown')
    chain.tqdm_position = param_run.get('tqdm_position', 0)
    chain.seed = param_run.get('seed', 'Unknown')

    # Run the chain
    result = chain.run(
        n_iter=param_run['n_iter'], 
        RF=rf1, 
        only_save_last_bed=param_run['only_save_last_bed'], 
        info_per_iter=param_run['info_per_iter'], 
        plot=param_run['plot'], 
        progress_bar=param_run['progress_bar']
        )
    
    # Unpack results
    beds, loss_mc, loss_data, loss, steps, resampled_times, blocks_used = result

    # Save the state of the random generator
    with open(seed_folder / 'RNGState_RandField.txt', "w") as file: 
        json.dump(rf1.rng.bit_generator.state, file)
    with open(seed_folder / 'RNGState_chain.txt', "w") as file: 
        json.dump(chain.rng.bit_generator.state,file)

    # Combine with previous results if they exist
    if previous_results is not None:
        # Append new results to previous results
        loss_mc = np.concatenate([previous_results['loss_mc'], loss_mc])
        loss_data = np.concatenate([previous_results['loss_data'], loss_data])
        loss = np.concatenate([previous_results['loss'], loss])
        steps = np.concatenate([previous_results['steps'], steps])
        resampled_times = previous_results['resampled_times'] + resampled_times
        blocks_used = np.vstack([previous_results['blocks_used'], blocks_used])
    
    # Calculate new cumulative iteration count
    cumulative_iters += n_iter
    iteration_label = f'{cumulative_iters // 1000}k'
    
    # Save all outputs with updated iteration label
    np.save(seed_folder / f'bed_{iteration_label}.npy', beds)

    np.savez_compressed(
        seed_folder / f'results_{iteration_label}.npz',
        loss_mc=loss_mc,
        loss_data=loss_data,
        loss=loss,
        steps=steps,
        resampled_times=resampled_times,
        blocks_used=blocks_used
    )
    
    # Delete old files after successfully saving new ones
    for file_path in files_to_delete:
        if file_path.exists():
            file_path.unlink()
            
    np.savetxt(seed_folder / 'current_iter.txt', [cumulative_iters], fmt='%d')

    return result

    
def smallScaleChain_mp(n_chains, n_workers, smallScaleChain, initial_beds, ssc_rng_seeds, lsc_seed_map, n_iters, output_path='./Data/output'):
    '''
    function to run multiple small scale chain using multiprocessing

    Parameters
    ----------
    n_chains (int): the number of chains this multiprocessing choose to run
    n_workers (int): the number of processes the multiprocessing function create. Must be less than the number of CPUs you have
    smallScaleChain (MCMC.chain_sgs): an existing small scale chain that has already been set-up
    initial_beds (list): a list of subglacial topography (each of which are a 2D numpy array) used to initialize each chain
    ssc_rng_seeds (list): a list of int used to initialize the random number generator of each chain
    lsc_rng_seed (int): rng seed for the parent lsc that will be used to find where to save results
    n_iters (int): a list of number of iterations runned for each chain

    Returns
    -------
    result: a list of results from all the chains runned.

    '''
    # Clear the console for the progress bars
    os.system('cls' if os.name == 'nt' else 'clear')

    tic = time.time()

    params = []
    # retrive parameters from the existing chain
    example_chain = smallScaleChain.__dict__

    # modify some of the parameters based on the input ssc_rng_seeds, initial_beds, and n_iters
    for i in range(n_chains):
        chain_param = deepcopy(example_chain)
        chain_param['rng_seed'] = ssc_rng_seeds[i]
        chain_param['initial_bed'] = initial_beds[i]

        run_param = {}
        run_param['n_iter'] = n_iters[i]
        # some display parameters are fixed.
        run_param['only_save_last_bed'] = True
        run_param['info_per_iter'] = 10
        run_param['plot'] = False
        run_param['progress_bar'] = False
        run_param['chain_id'] = i
        run_param['tqdm_position'] = i + 2 # 2 lines for header
        run_param['ssc_seed'] = ssc_rng_seeds[i]
        run_param['lsc_seed'] = lsc_seed_map[i]
        run_param['output_path'] = str(Path(output_path) / 'LargeScaleChain' / str(lsc_seed_map[i])[:6] / 'SmallScaleChain')
        params.append([deepcopy(chain_param), deepcopy(run_param)])

    # Print header and reserve space for progress bars
    print('Running MCMC chains...')
    print('\n' * (n_chains + 1))
    sys.stdout.flush() # force output into the terminal

    # the multiprocessing step
    with mp.Pool(n_workers) as pool:
        result = pool.starmap(msc_run_wrapper, params)


    print('\n')
    print(r'''
           _o                  _                 _o_   o   o
      o    (^)  _             (o)    >')         (^)  (^) (^)
   _ (^) ('>~ _(v)_      _   //-\\   /V\      ('> ~ __.~   ~
 ('v')~ // \\  /-\      (.)-=_\_/)   (_)>     (V)  ~  ~~ /__ /\
//-=-\\ (\_/) (\_/)      V \ _)>~    ~~      <(__\[     ](__=_')
(\_=_/)  ^ ^   ^ ^       ~  ~~                ~~~~        ~~~~~
_^^_^^   __  ..-.___..---I~~~:_  .__...--.._.;-'I~~~~-.____...;-
 |~|~~~~~| ~~|  _   |    |  _| ~~|  |  |  |  |_ |      | _ |  |
_.-~~_.-~-~._.-~~._.-~-~_.-~~_.-~~_.-~-~._.-~~._.-~-~_.-~~_.-~-~
    ''')

    toc = time.time()
    print(f'Completed in {toc-tic} seconds')

    return result


def msc_run_wrapper(param_chain, param_run):
    '''
    A function used to initialize chain by input parameters and run the chains

    Parameters
    ----------
    param_chain (dict): Dictionary containing parameters needed to initialize chain
    param_rf (dict): Dictionary containing parameters needed to initialize random field
    param_run (dict): Dictionary containing parameters needed to run chain

    Returns
    -------
    result (tuple): A tuple containing the results of the run

    '''

    # Suppress initialization prints from workers
    old_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')

    chain = MCMC.init_msc_chain_by_instance(param_chain)

    # Restore stdout after initialization
    sys.stdout.close()
    sys.stdout = old_stdout

    # Setup output path
    output_path = param_run.get(
        'output_path', 
        './Data/LargeScaleChain/'+str(param_run['lsc_seed'])[:6]+'/SmallScaleChain'
        )
    seed = param_run['ssc_seed']
    n_iter = param_run['n_iter']
    seed_folder = Path(output_path) / f'{str(seed)[:6]}'

    # Check for existing bed files (to resume progress)
    exist_chain = list(seed_folder.glob('current_iter.txt'))
    cumulative_iters = 0
    previous_results = None
    files_to_delete = []

    if exist_chain:
        cumulative_iters = int(np.loadtxt(exist_chain[0]))
        iter_count = int(cumulative_iters / 1000)
        most_recent_bed = np.load(seed_folder / f'bed_{iter_count}k.npy')
        chain.initial_bed = most_recent_bed
        with np.load(seed_folder / f'results_{iter_count}k.npz') as results_data:
            previous_results = {
                'loss_mc': results_data['loss_mc'].copy(),
                'loss_data': results_data['loss_data'].copy(),
                'loss': results_data['loss'].copy(),
                'steps': results_data['steps'].copy(),
                'resampled_times': results_data['resampled_times'].copy(),
                'blocks_used': results_data['blocks_used'].copy()
            }
        files_to_delete = [
            seed_folder / f'results_{iter_count}k.npz',
            seed_folder / 'current_iter.txt'
        ]
        with open(seed_folder / 'RNGState_chain.txt', 'r') as file:
            chain.rng.bit_generator.state = json.load(file)

    # Store positioning info
    chain.chain_id = param_run.get('chain_id', 'Unknown')
    chain.tqdm_position = param_run.get('tqdm_position', 0)
    chain.seed = param_run.get('ssc_seed', 'Unkown')

    # Run the chain
    result = chain.run(
        n_iter=param_run['n_iter'], 
        only_save_last_bed=param_run['only_save_last_bed'],
        info_per_iter=param_run['info_per_iter'], 
        plot=param_run['plot'], 
        progress_bar=param_run['progress_bar']
        )
    
    # Unpack results
    beds, loss_mc, loss_data, loss, steps, resampled_times, blocks_used = result

    with open(seed_folder / 'RNGState_chain.txt', "w") as file: 
        json.dump(chain.rng.bit_generator.state,file)

    # Combine with previous results if they exist
    if previous_results is not None:
        # Append new results to previous results
        loss_mc = np.concatenate([previous_results['loss_mc'], loss_mc])
        loss_data = np.concatenate([previous_results['loss_data'], loss_data])
        loss = np.concatenate([previous_results['loss'], loss])
        steps = np.concatenate([previous_results['steps'], steps])
        resampled_times = previous_results['resampled_times'] + resampled_times
        blocks_used = np.vstack([previous_results['blocks_used'], blocks_used])

    # Calculate new cumulative iteration count
    cumulative_iters += n_iter
    iteration_label = f'{cumulative_iters // 1000}k'

    # Save all outputs with updated iteration label
    np.save(seed_folder / f'bed_{iteration_label}.npy', beds)

    np.savez_compressed(
        seed_folder / f'results_{iteration_label}.npz',
        loss_mc=loss_mc,
        loss_data=loss_data,
        loss=loss,
        steps=steps,
        resampled_times=resampled_times,
        blocks_used=blocks_used
    )

    # Delete old files after successfully saving new ones
    for file_path in files_to_delete:
        if file_path.exists():
            file_path.unlink()

    np.savetxt(seed_folder / 'current_iter.txt', [cumulative_iters], fmt='%d')

    return result


if __name__ == '__main__':
    # Set file paths here
    #NOTE use r string literals in case backslashes are used
    glacier_data_path = Path(r'DenmanDataGridded.csv')
    seed_file_path = Path(r'../200_seeds.txt')
    output_path = Path(r'./Data/Denman')

    n_iter = 1000

    # Index range of LSCs to run SSCs for (0-9 inclusive)
    lsc_starting_idx = 0
    lsc_ending_idx = 4

    #NOTE n_chains is calculated by subtracting the starting index from the ending index
    n_workers = psutil.cpu_count(logical=False)-1

    # load compiled bed elevation measurements
    df = pd.read_csv(glacier_data_path)

    rng_seed = 0

    # create a grid of x and y coordinates
    x_uniq = np.unique(df.x)
    y_uniq = np.unique(df.y)

    xmin = np.min(x_uniq)
    xmax = np.max(x_uniq)
    ymin = np.min(y_uniq)
    ymax = np.max(y_uniq)

    cols = len(x_uniq)
    rows = len(y_uniq)

    resolution = 500

    xx, yy = np.meshgrid(x_uniq, y_uniq)

    # load other data
    dhdt = df['dhdt'].values.reshape(xx.shape)
    smb = df['smb'].values.reshape(xx.shape)
    velx = df['velx'].values.reshape(xx.shape)
    vely = df['vely'].values.reshape(xx.shape)
    bedmap_mask = df['bedmap_mask'].values.reshape(xx.shape)
    bedmachine_thickness = df['bedmachine_thickness'].values.reshape(xx.shape)
    bedmap_surf = df['bedmap_surf'].values.reshape(xx.shape)
    highvel_mask = df['highvel_mask'].values.reshape(xx.shape)
    bedmap_bed = df['bedmap_bed'].values.reshape(xx.shape)

    # notice that this didn't recover bedmachine bed for ocean bathymetry or sub-ice-shelf bathymetry
    bedmachine_bed = bedmap_surf - bedmachine_thickness

    # create conditioning data
    # bed elevation measurement in grounded ice region, and bedmachine bed topography elsewhere
    cond_bed = np.where(
        bedmap_mask == 1, df['bed'].values.reshape(xx.shape), bedmap_bed)
    df['cond_bed'] = cond_bed.flatten()

    # create a mask of conditioning data
    data_mask = ~np.isnan(cond_bed)

    # Read all seeds
    with open(seed_file_path, 'r') as f:
        rng_seeds = [int(line.strip()) for line in f.readlines()]

    lsc_indices = range(lsc_starting_idx, lsc_ending_idx+1)
    n_lsc_selected = len(lsc_indices)
    n_ssc_total = n_lsc_selected * 10 # 10 SSC per LSC

    # Build flat lists across all selected LSCs
    initial_beds = []
    ssc_seeds = []
    lsc_seed_map = []
    lsc_iter_map = []

    for lsc_idx in lsc_indices:
        lsc_seed = rng_seeds[lsc_idx]
        lsc_path = output_path / 'LargeScaleChain' / str(lsc_seed)[:6]

        bed_files = sorted(
            lsc_path.glob('bed_*.npy'),
            key=lambda f: int(f.stem.split('_')[1].replace('k', ''))
        )

        ssc_seeds_for_lsc = rng_seeds[
            10 + lsc_idx * 10 :
            10 + lsc_idx * 10 + 10
        ]

        for i, bed_file in enumerate(bed_files):
            lsc_iter = int(bed_file.stem.split('_')[1].replace('k', '')) * 1000
            
            one_initial_bed = np.load(bed_file) 
            thickness = bedmap_surf - one_initial_bed
            one_initial_bed = np.where((thickness <= 0) & (bedmap_mask == 1), bedmap_surf - 1, one_initial_bed)
            initial_beds.append(one_initial_bed)
            
            ssc_seeds.append(ssc_seeds_for_lsc[i])
            lsc_seed_map.append(lsc_seed)
            lsc_iter_map.append(lsc_iter)

            ssc_folder = lsc_path / 'SmallScaleChain' / str(ssc_seeds_for_lsc[i])[:6]
            ssc_folder.mkdir(parents=True, exist_ok=True)
            np.savetxt(ssc_folder / 'init_iter.txt', [lsc_iter], fmt='%d')

    # TODO: This needs to be different
    initial_bed = initial_beds[0]
    thickness = bedmap_surf - initial_bed
    # make sure every topography in the grounded ice region is below ice surface
    initial_bed = np.where((thickness <= 0) & (
        bedmap_mask == 1), bedmap_surf-1, initial_bed)

    # sigma here control the smoothness of the trend
    trend = sp.ndimage.gaussian_filter(initial_bed, sigma=10)

    # normalize the conditioning bed data, saved to df['Nbed']
    df['cond_bed_residual'] = df['cond_bed'].values-trend.flatten()
    data = df['cond_bed_residual'].values.reshape(-1, 1)
    # data used to evaluate the distribution. We use all data in the initial bed
    data_for_distribution = (initial_bed - trend).reshape((-1, 1))
    nst_trans = QuantileTransformer(n_quantiles=1000, output_distribution="normal",
                                    subsample=None, random_state=rng_seed).fit(data_for_distribution)
    # normalize all data in df['cond_bed_residual']
    transformed_data = nst_trans.transform(data)
    df['Nbed_residual'] = transformed_data

    # randomly drop out 50% of coordinates. Decrease this value if you have a lot of data and it takes a long time to run
    df_sampled = df.sample(frac=0.5, random_state=rng_seed)
    df_sampled = df_sampled[df_sampled["cond_bed_residual"].isnull() == False]
    df_sampled = df_sampled[df_sampled["bedmap_mask"] == 1]

    # compute experimental (isotropic) variogram
    coords = df_sampled[['x', 'y']].values
    values = df_sampled['Nbed_residual']

    maxlag = 20000      # maximum range distance
    # num of bins (try decreasing if this is taking too long)
    n_lags = 70

    # compute variogram
    V1 = skg.Variogram(coords, values, bin_func='even',
                       n_lags=n_lags, maxlag=maxlag, normalize=False,
                       model='matern')

    # extract variogram values
    xdata = V1.bins
    ydata = V1.experimental

    # Notice: because we randomly drop out some data, the calculation of V1_p won't always obtain the same result
    # To ensure reproducibility of your work, please use a consistent set of V1_p throughout different chains
    V1_p = V1.parameters

    grounded_ice_mask = (bedmap_mask == 1)

    # initialize the small scale chain to be used as an example to initialize other small scale chain
    smallScaleChain = MCMC.chain_sgs(xx, yy, initial_bed, bedmap_surf, velx,
                                     vely, dhdt, smb, cond_bed, data_mask, grounded_ice_mask, resolution)
    # set the update region
    smallScaleChain.set_update_region(True, highvel_mask)

    # get mass flux residuals for bedmachien as a reference
    mc_res_bm = Topography.get_mass_conservation_residual(
        bedmachine_bed, bedmap_surf, velx, vely, dhdt, smb, resolution)

    # in multiprocessing, we choose to only use mass flux residual loss in squared sum (Gaussian distribution)
    smallScaleChain.set_loss_type(sigma_mc=5, massConvInRegion=True)

    # set up the block sizes
    min_block_x = 5
    max_block_x = 20
    min_block_y = 5
    max_block_y = 20
    smallScaleChain.set_block_sizes(
        min_block_x, max_block_x, min_block_y, max_block_y)

    # set up normal score transformation, the trend, the variogram parameters, and the sgs paramters
    smallScaleChain.set_normal_transformation(nst_trans, do_transform=True)

    smallScaleChain.set_trend(trend=trend, detrend_map=True)

    smallScaleChain.set_variogram(
        'Matern', V1_p[0], V1_p[1], 0, isotropic=True, vario_smoothness=V1_p[2])

    smallScaleChain.set_sgs_param(48, 30e3, sgs_rand_dropout_on=False)

    # set up the random generator used in the chain
    # in multiprocessing, the random generator in here will be replaced by rng_seeds later
    smallScaleChain.set_random_generator(rng_seed=rng_seed)
    
    # number of iterations used to run each chain
    n_iters = [n_iter]*n_ssc_total

    result = smallScaleChain_mp(n_ssc_total, n_workers, smallScaleChain, initial_beds, ssc_seeds, lsc_seed_map, n_iters, output_path = output_path)
