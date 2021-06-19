import tensorflow as tf
import numpy as np

import sys
sys.path.append('/esarchive/scratch/cgomez/src/ecubevis/')
import ecubevis as ecv

from .utils import crop_array, resize_array, checkarg_model


def create_pair_hr_lr(
    array, 
    scale, 
    patch_size, 
    topography=None, 
    landocean=None, 
    tuple_predictors=None, 
    model='resnet_spc',
    debug=False, 
    interpolation='bicubic'):
    """
    Create a pair of HR and LR square sub-patches. In this case, the LR 
    corresponds to a coarsen version of the HR reference with land-ocean mask,
    topography and auxiliary predictors added as "image channels".

    Parameters
    ----------
    array : np.ndarray
        HR gridded data.
    scale : int
        Scaling factor.
    patch_size : int or None
        Size of the square patches to be extracted.
    topography : None or 2D ndarray, optional
        Elevation data.
    landocean : None or 2D ndarray, optional
        Binary land-ocean mask.
    tuple_predictors : tuple of ndarrays, optional
        Tuple of 3D ndarrays [lat, lon, 1] corresponding to predictor variables,
        in low (target) resolution. Assumed to be in LR for r-spc. To be 
        concatenated to the LR version of `array`.
    model : str, optional
        String with the name of the model architecture, either 'resnet_spc', 
        'resnet_int' or 'resnet_rec'.
    interpolation : str, optional
        Interpolation used when upsampling/downsampling the training samples.
        By default 'bicubic'. 
    debug : bool, optional
        Whether to show plots and debugging information.
    """
    hr_array = np.squeeze(array)
    hr_y, hr_x = hr_array.shape

    if model == 'resnet_int': 
        lr_x, lr_y = int(hr_x / scale), int(hr_y / scale) 
        # whole image is downsampled and upsampled via interpolation
        lr_array_resized = resize_array(hr_array, (lr_x, lr_y), interpolation)
        lr_array_resized = resize_array(lr_array_resized, (hr_x, hr_y), interpolation)
        if patch_size is not None:
            # cropping both hr_array and lr_array (same sizes)
            hr_array, crop_y, crop_x = crop_array(np.squeeze(hr_array), patch_size, 
                                                  yx=None, position=True)
            lr_array = crop_array(np.squeeze(lr_array_resized), patch_size, yx=(crop_y, crop_x))
        else:
            lr_array = lr_array_resized
        hr_array = np.expand_dims(hr_array, -1)
        lr_array = np.expand_dims(lr_array, -1)
    elif model in ['resnet_spc', 'resnet_rec']:
        if patch_size is not None:
            lr_x, lr_y = int(patch_size / scale), int(patch_size / scale) 
        else:
            lr_x, lr_y = int(hr_x / scale), int(hr_y / scale)

    if tuple_predictors is not None:
        # turned into a 3d ndarray, [lat, lon, variables]
        array_predictors = np.asarray(tuple_predictors)
        array_predictors = np.rollaxis(np.squeeze(array_predictors), 0, 3)

    if model == 'resnet_int':
        if tuple_predictors is not None:
            # upsampling the lr predictors
            array_predictors = resize_array(array_predictors, (hr_x, hr_y), interpolation)
            if patch_size is not None:
                cropsize = patch_size
                # cropping predictors 
                lr_array_predictors, crop_y, crop_x = crop_array(array_predictors, cropsize,
                                                                 yx=(crop_y, crop_x), 
                                                                 position=True)
            # concatenating the predictors to the lr image
            lr_array = np.concatenate([lr_array, lr_array_predictors], axis=2)
    elif model in ['resnet_spc', 'resnet_rec']:
        if tuple_predictors is not None:
            if patch_size is not None:
                cropsize = lr_x
                # cropping first the predictors 
                lr_array_predictors, crop_y, crop_x = crop_array(array_predictors, cropsize,
                                                                 yx=None, position=True)
                crop_y = int(crop_y * scale)
                crop_x = int(crop_x * scale)
                hr_array = crop_array(np.squeeze(hr_array), patch_size, yx=(crop_y, crop_x))   
            lr_array = resize_array(hr_array, (lr_x, lr_y), interpolation)       
            hr_array = np.expand_dims(hr_array, -1)
            lr_array = np.expand_dims(lr_array, -1) 
            # concatenating the predictors to the lr image
            lr_array = np.concatenate([lr_array, lr_array_predictors], axis=2)
        else:
            if patch_size is not None:
                # cropping the hr array
                hr_array, crop_y, crop_x = crop_array(hr_array, patch_size, yx=None, position=True)
            # downsampling the hr array to get lr_array
            lr_array = resize_array(hr_array, (lr_x, lr_y), interpolation)    
            hr_array = np.expand_dims(hr_array, -1)
            lr_array = np.expand_dims(lr_array, -1)

    if topography is not None:
        if patch_size is not None:
            topo_hr = crop_array(np.squeeze(topography), patch_size, yx=(crop_y, crop_x))
        else:
            topo_hr = topography
        if model in ['resnet_spc', 'resnet_rec']:  # downsizing the topography
            topo_lr = resize_array(topo_hr, (lr_x, lr_y), interpolation)
            lr_array = np.concatenate([lr_array, np.expand_dims(topo_lr, -1)], axis=2)
        elif model == 'resnet_int':  # topography in HR 
            lr_array = np.concatenate([lr_array, np.expand_dims(topo_hr, -1)], axis=2)

    if landocean is not None:
        if patch_size is not None:
            landocean_hr = crop_array(np.squeeze(landocean), patch_size, yx=(crop_y, crop_x))
        else:
            landocean_hr = landocean
        if model in ['resnet_spc', 'resnet_rec']:  # downsizing the land-ocean mask
            # integer array can only be interpolated with nearest method
            landocean_lr = resize_array(landocean_hr, (lr_x, lr_y), interpolation='nearest')
            lr_array = np.concatenate([lr_array, np.expand_dims(landocean_lr, -1)], axis=2)
        elif model == 'resnet_int':  # lando in HR 
            lr_array = np.concatenate([lr_array, np.expand_dims(landocean_hr, -1)], axis=2)
    
    hr_array = np.asarray(hr_array, 'float32')
    lr_array = np.asarray(lr_array, 'float32')

    if debug:
        print(f'HR image: {hr_array.shape}, LR image {lr_array.shape}')
        if patch_size is not None:
            print(f'Crop X,Y: {crop_x}, {crop_y}')

        ecv.plot_ndarray((array[:,:,0]), dpi=60, interactive=False)
        
        if topography is not None or landocean is not None or tuple_predictors is not None:
            lr_array_plot = np.squeeze(lr_array)[:,:,0]
        else:
            lr_array_plot = np.squeeze(lr_array)
        ecv.plot_ndarray((np.squeeze(hr_array), lr_array_plot), 
                         dpi=80, interactive=False, 
                         subplot_titles=('HR cropped image', 'LR cropped image'))
        
        if model in ['resnet_spc', 'resnet_rec']:
            if topography is not None:
                ecv.plot_ndarray((topo_hr, topo_lr), 
                                interactive=False, dpi=80, 
                                subplot_titles=('HR Topography', 'LR Topography'))
            
            if landocean is not None:
                ecv.plot_ndarray((landocean_hr, landocean_lr), 
                                interactive=False, dpi=80, 
                                subplot_titles=('HR Land Ocean mask', 'LR  Land Ocean mask'))
        elif model == 'resnet_int':
            if topography is not None:
                ecv.plot_ndarray(topography, interactive=False, dpi=80, 
                                 subplot_titles=('HR Topography'))
        
            if landocean is not None:
                ecv.plot_ndarray(landocean, interactive=False, dpi=80, 
                                 subplot_titles=('HR Land Ocean mask'))

        if tuple_predictors is not None:
            ecv.plot_ndarray(np.rollaxis(lr_array_predictors, 2, 0), dpi=80, interactive=False, 
                             subplot_titles=('LR cropped predictors'), multichannel4d=True)

    return hr_array, lr_array


class DataGenerator(tf.keras.utils.Sequence):
    """
    A sequence structure guarantees that the network will only train once on 
    each sample per epoch which is not the case with generators. 
    Every Sequence must implement the __getitem__ and the __len__ methods. If 
    you want to modify your dataset between epochs you may implement 
    on_epoch_end. The method __getitem__ should return a complete batch.

    """
    def __init__(self, 
        array, 
        scale=4, 
        batch_size=32, 
        patch_size=40,
        topography=None, 
        landocean=None, 
        predictors=None,
        model='resnet_spc', 
        interpolation='bicubic'
        ):
        """
        Parameters
        ----------
        model : {'resnet_spc', 'resnet_int', 'resnet_rec'}
            Name of the model architecture.
        predictors : tuple of 4D ndarray 
            Tuple of predictor ndarrays with dims [nsamples, lat, lon, 1].

        TO-DO
        -----
        instead of the in-memory array, we could input the path and load the 
        netcdf files lazily or memmap a numpy array
        """
        self.array = array
        self.batch_size = batch_size
        self.scale = scale
        self.patch_size = patch_size
        self.topography = topography
        self.landocean = landocean
        self.predictors = predictors
        self.model = checkarg_model(model)
        self.interpolation = interpolation
        self.n = array.shape[0]
        self.indices = np.random.permutation(self.n)

        if self.model in ['resnet_spc', 'resnet_rec'] and patch_size is not None:
            if not self.patch_size % self.scale == 0:
                raise ValueError('`patch_size` must be divisible by `scale`')

    def __len__(self):
        """
        Defines the number of batches the DataGenerator can produce per epoch.
        A common practice is to set this value to n_samples / batch_size so that 
        the model sees the training samples at most once per epoch. 
        """
        n_batches = self.n // self.batch_size
        return n_batches

    def __getitem__(self, index):
        """
        Generate one batch of data as (X, y) value pairs where X represents the 
        input and y represents the output.
        """
        self.batch_rand_idx = self.indices[
            index * self.batch_size : (index + 1) * self.batch_size]
        batch_hr_images = []
        batch_lr_images = []

        for i in self.batch_rand_idx:   
            if self.predictors is not None:
                # we pass a tuple of 3D ndarrays [lat, lon, 1]
                tuple_predictors = tuple([var[i] for var in self.predictors])
            else:
                tuple_predictors = None

            res = create_pair_hr_lr(
                array=self.array[i],
                scale=self.scale, 
                patch_size=self.patch_size, 
                topography=self.topography, 
                landocean=self.landocean, 
                tuple_predictors=tuple_predictors,
                model=self.model,
                interpolation=self.interpolation)
            hr_array, lr_array = res
            batch_lr_images.append(lr_array)
            batch_hr_images.append(hr_array)

        batch_lr_images = np.asarray(batch_lr_images)
        batch_hr_images = np.asarray(batch_hr_images) 
        return [batch_lr_images], [batch_hr_images]

    def on_epoch_end(self):
        """
        """
        np.random.shuffle(self.indices)

