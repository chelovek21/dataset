""" Contains Batch classes for images """

import os   # pylint: disable=unused-import

try:
    import blosc   # pylint: disable=unused-import
except ImportError:
    pass
import numpy as np
try:
    import PIL.Image
except ImportError:
    pass
try:
    import scipy.ndimage
except ImportError:
    pass
try:
    import cv2
except ImportError:
    pass

from .batch import Batch
from .decorators import action, inbatch_parallel, any_action_failed


class ImagesBatch(Batch):
    """ Batch class for 2D images """
    def __init__(self, index, preloaded=None):
        super().__init__(index, preloaded)
        self._new_attr = None

    @property
    def data(self):
        data = super().data
        return data if data is not None else tuple([None, None, None])

    @property
    def images(self):
        """ Images """
        return self.data[0] if self.data is not None else None

    @images.setter
    def images(self, value):
        """ Set images """
        data = list(self.data)
        data[0] = value
        self._data = data

    @property
    def labels(self):
        """ Labels for images """
        return self.data[1] if self.data is not None else None

    @labels.setter
    def labels(self, value):
        """ Set labels """
        data = list(self.data)
        data[1] = value
        self._data = data

    @property
    def masks(self):
        """ Masks for images """
        return self.data[2] if self.data is not None else None

    @masks.setter
    def masks(self, value):
        """ Set masks """
        data = list(self.data)
        data[3] = value
        self._data = data

    def assemble(self, all_res, *args, **kwargs):
        """ Assemble the batch after a parallel action """
        _ = args, kwargs
        if any_action_failed(all_res):
            raise ValueError("Could not assemble the batch", self.get_errors(all_res))

        attr = kwargs.get('attr', 'images')
        if isinstance(all_res[0], PIL.Image.Image):
            setattr(self, attr, all_res)
        else:
            setattr(self, attr, np.transpose(np.dstack(all_res), (2, 0, 1)))
        return self

    @action
    def convert_to_PIL(self, attr='images'):   # pylint: disable=invalid-name
        """ Convert batch data to PIL.Image format """
        self._new_attr = list(None for _ in self.indices)
        self.apply_transform(attr, '_new_attr', PIL.Image.fromarray)
        setattr(self, attr, self._new_attr)
        return self

    @action
    @inbatch_parallel(init='images', post='assemble')
    def resize(self, image, shape, method=None):
        """ Resize all images in the batch
        if batch contains PIL images or if method is 'PIL',
        uses PIL.Image.resize, otherwise scipy.ndimage.zoom
        We recommend to install a very fast Pillow-SIMD fork """
        if isinstance(image, PIL.Image.Image):
            return image.resize(shape, PIL.Image.ANTIALIAS)
        else:
            if method == 'PIL':
                new_image = PIL.Image.fromarray(image).resize(shape, PIL.Image.ANTIALIAS)
                new_arr = np.fromstring(new_image.tobytes(), dtype=image.dtype)
                if len(image.shape) == 2:
                    new_arr = new_arr.reshape(new_image.height, new_image.width)
                elif len(image.shape) == 3:
                    new_arr = new_arr.reshape(new_image.height, new_image.width, -1)
                return new_arr
            elif method == 'cv2':
                new_shape = shape[1], shape[0]
                return cv2.resize(image, new_shape, interpolation=cv2.INTER_CUBIC)
            else:
                factor = 1. * np.asarray(shape) / np.asarray(image.shape)
                return scipy.ndimage.zoom(image, factor, order=3)

    @action
    def load(self, src, fmt=None):
        """ Load data """
        if fmt is None:
            if isinstance(src, tuple):
                self._data = tuple(src[i][self.indices] if len(src) > i else None for i in range(3))
            else:
                self._data = src[self.indices], None, None
        else:
            raise ValueError("Unsupported format:", fmt)
        return self

    @action
    def dump(self, dst, fmt=None):
        """ Saves data to a file or array """
        _ = dst, fmt
        return self

    @action
    @inbatch_parallel(init='indices')
    def apply_transform(self, ix, src, dst, func, *args, **kwargs):
        """ Apply a function to each item of the batch """
        if src is None:
            all_args = args
        else:
            src_attr = getattr(self, src)
            all_args = tuple(src_attr[pos], *args)
        dst_attr = getattr(self, dst)
        pos = self.index.get_pos(ix)
        dst_attr[pos] = func(*all_args, **kwargs)

    @action
    def apply_transform_all(self, src, dst, func, *args, **kwargs):
        """ Apply a function all item of the batch """
        if src is None:
            all_args = args
        else:
            src_attr = getattr(self, src)
            all_args = tuple(src_attr, *args)
        dst_attr = getattr(self, dst)
        dst_attr = func(*all_args, **kwargs)
