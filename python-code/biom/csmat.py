#!/usr/bin/env python

from numpy import array, ndarray, concatenate, argsort, searchsorted, uint32, \
        zeros
from operator import itemgetter
from biom.util import flatten
from biom.exception import TableException
from itertools import izip

__author__ = "Daniel McDonald"
__copyright__ = "Copyright 2012, BIOM-Format Project"
__credits__ = ["Daniel McDonald"] 
__license__ = "GPL"
__url__ = "http://biom-format.org"
__version__ = "1.0.0-dev"
__maintainer__ = "Daniel McDonald"
__email__ = "daniel.mcdonald@colorado.edu"

class CSMat():
    """Support for compressed sparse and coordinate list formats

    Must specify rows and columns in advance

    Object cannot "grow" in shape

    enable_indices is ignored
    """

    def __init__(self, rows, cols, dtype=float, enable_indices=True):
        self.shape = (rows, cols) 
        self.dtype = dtype # casting is minimal, trust the programmer...

        # yale, or csr/csc format

        # coordinate list 
        self._coo_values = []
        self._coo_rows = []
        self._coo_cols = []

        self._order = "coo"
        self._values = array([], dtype=dtype)
        self._pkd_ax = array([], dtype=uint32)
        self._unpkd_ax = array([], dtype=uint32)

    def bulkCOOUpdate(self, rows, cols, values):
        """Expects 3 iterables in aligned by index"""
        self._coo_values.extend(values)
        self._coo_rows.extend(rows)
        self._coo_cols.extend(cols)

    def update(self, data):
        """Update from a dict"""
        for (r,c),v in data.iteritems():
            self[(r,c)] = v

    def hasUpdates(self):
        """Returns true if it appears there are updates"""
        if len(self._coo_values) != 0:
            return True
        else:
            return False

    def _get_size(self):
        """Returns the number of elements stored"""
        if self.hasUpdates():
            self.absorbUpdates()

        if self._order == "coo":
            return len(self._coo_values)
        else:
            return self._pkd_ax[-1]
    size = property(_get_size)

    def convert(self, to_order):
        """Converts to csc <-> csr, csc <-> coo, csr <-> coo"""
        if self._order == to_order:
            return

        if self._order == "coo":
            self._buildCSfromCOO(to_order)
        else:
            if to_order == "coo":
                self._buildCOOfromCS()
            else:
                self._buildCSfromCS()

    def absorbUpdates(self):
        """If there are COO values not in CS form, pack them in"""
        if self._order == 'coo':
            return
        
        if not self._coo_values:
            return

        # possibly a better way to do this
        order = self._order
        self.convert("coo")
        self.convert(order)

    def _buildCSfromCS(self):
        """Convert csc <-> csr"""
        expanded = self._expand_compressed(self._pkd_ax)
        if self._order == "csr":
            csc = self._toCSC(expanded, self._unpkd_ax, self._values)
            self._pkd_ax, self._unpkd_ax, self._values = csc 
            self._order = "csc"

        elif self._order == "csc":
            csr = self._toCSR(self._unpkd_ax, expanded, self._values)
            self._pkd_ax, self._unpkd_ax, self._values = csr
            self._order = "csr"

    def _expand_compressed(self, pkd_ax):
        """Expands oacked"""
        expanded = zeros(pkd_ax[-1], dtype=uint32)
        last_idx = 0
        pos = uint32(0)
        for idx in pkd_ax[1:]:
            expanded[last_idx:idx] = pos
            pos += 1
            last_idx = idx
        return expanded
            
    def _buildCOOfromCS(self):
        """Constructs a COO representation from CSC or CSR
        
        Invalidates existing CSC or CSR representation
        """
        coo = self._toCOO(self._pkd_ax,self._unpkd_ax,self._values,self._order)
        coo_rows, coo_cols, coo_values = coo
        self._coo_rows.extend(coo_rows)
        self._coo_cols.extend(coo_cols)
        self._coo_values.extend(coo_values)

        self._values = array([], dtype=self.dtype)
        self._pkd_ax = array([], dtype=uint32)
        self._unpkd_ax = array([], dtype=uint32)
        
        self._order = "coo"

    def _toCOO(self, pkd_ax, unpkd_ax, values, current_order):
        """Returns rows, cols, values"""
        coo_values = list(values)
        expanded_ax = list(self._expand_compressed(pkd_ax))
        
        if current_order == 'csr':
            coo_cols = list(unpkd_ax)
            coo_rows = expanded_ax

        elif current_order == 'csc':
            coo_rows = list(unpkd_ax)
            coo_cols = expanded_ax
        else:
            raise ValueError, "Unknown order: %s" % order

        return (coo_rows, coo_cols, coo_values)
        
    def _buildCSfromCOO(self, order):
        """Build a sparse representation

        order is either csc or csr

        Returns instantly if is stable, throws ValueError if the sparse rep
        is already build
        """
        if order == 'csr':
            csr = self._toCSR(self._coo_rows, self._coo_cols, self._coo_values)
            self._pkd_ax, self._unpkd_ax, self._values = csr
        elif order == 'csc':
            csc = self._toCSC(self._coo_rows, self._coo_cols, self._coo_values)
            self._pkd_ax, self._unpkd_ax, self._values = csc 
        else:
            raise ValueError, "Unknown order: %s" % order

        self._coo_rows = []
        self._coo_cols = []
        self._coo_values = []
        self._order = order

    def _toCSR(self, rows, cols, values):
        """Returns packed_axis, unpacked_axis and values"""
        values = array(values, dtype=self.dtype)
        unpkd_ax = array(cols, dtype=uint32)
        tmp_rows = array(rows, dtype=uint32)

        order = argsort(tmp_rows)
        values = values.take(order)
        tmp_rows = tmp_rows.take(order)
        unpkd_ax = unpkd_ax.take(order)

        v_last = tmp_rows[0]
        pkd_ax = [0]
        pos = 0
        p_last = 0

        # determine starting values idx for each row
        # sort values and columns within each row
        for v in tmp_rows:
            if v != v_last:
                pkd_ax.append(pos)
                col_order = argsort(unpkd_ax[p_last:pos])
                unpkd_ax[p_last:pos] = unpkd_ax[p_last:pos].take(col_order)
                values[p_last:pos] = values[p_last:pos].take(col_order)
                v_last = v
                p_last = pos
            pos += 1
        # catch last column sort    
        col_order = argsort(unpkd_ax[p_last:pos])
        unpkd_ax[p_last:pos] = unpkd_ax[p_last:pos].take(col_order)
        values[p_last:pos] = values[p_last:pos].take(col_order)
        
        pkd_ax.append(pos)

        pkd_ax = array(pkd_ax, dtype=uint32)
        
        if len(pkd_ax) != (self.shape[0] + 1):
            raise ValueError, "Empty rows exist!"

        return (pkd_ax, unpkd_ax, values)

    def _toCSC(self, rows, cols, values):
        """Returns packed_axis, unpacked_axis, values"""
        values = array(values, dtype=self.dtype)
        unpkd_ax = array(rows, dtype=uint32)
        tmp_cols = array(cols, dtype=uint32)

        order = argsort(tmp_cols)
        values = values.take(order)
        tmp_cols = tmp_cols.take(order)
        unpkd_ax = unpkd_ax.take(order)

        v_last = tmp_cols[0]
        pkd_ax = [0]
        pos = 0
        p_last = 0
        ### gotta be something in numpy that does this...
        for v in tmp_cols:
            if v != v_last:
                pkd_ax.append(pos)
                row_order = argsort(unpkd_ax[p_last:pos])
                unpkd_ax[p_last:pos] = unpkd_ax[p_last:pos].take(row_order)
                values[p_last:pos] = values[p_last:pos].take(row_order)
                v_last = v
                p_last = pos
            pos += 1
        
        # catch last row sort
        row_order = argsort(unpkd_ax[p_last:pos])
        unpkd_ax[p_last:pos] = unpkd_ax[p_last:pos].take(row_order)
        values[p_last:pos] = values[p_last:pos].take(row_order)

        pkd_ax.append(pos)

        pkd_ax = array(pkd_ax, dtype=uint32)
        
        if len(pkd_ax) != (self.shape[1] + 1):
            raise ValueError, "Empty columns exist!"

        return (pkd_ax, unpkd_ax, values)

    def items(self):
        """Generater returning ((r,c),v)"""
        last = 0
        res = []
        if self._order == 'csr':
            for row,i in enumerate(self._pkd_ax[1:]):
                for col,val in izip(self._unpkd_ax[last:i],self._values[last:i]):
                    res.append(((row,col),val))
                last = i
        elif self._order == 'csc':
            for col,i in enumerate(self._pkd_ax[1:]):
                for row,val in izip(self._unpkd_ax[last:i],self._values[last:i]):
                    res.append(((row,col),val))
                last = i
        else:
            for r,c,v in izip(self._coo_rows, self._coo_cols, self._coo_values):
                res.append(((r,c),v))
        return res

    def __contains__(self, args):
        """Return True if args are in self, false otherwise"""
        if self._getitem(args) == (None, None, None):
            return False
        else:
            return True

    def _getitem(self, args):
        """Mine for an item
        
        if order is csc | csr, returns
        pkd_ax_idx, unpkd_ax_idx_, values_idx 

        if order is coo, returns
        rows_idx, cols_idx, values_idx (all the samething..)
        """
        row,col = args
        if self._order == 'csr':
            start = self._pkd_ax[row]
            stop = self._pkd_ax[row+1]
            for i,c in enumerate(self._unpkd_ax[start:stop]):
                if c == col:
                    return (row, start+i, start+i)

        elif self._order == 'csc':
            start = self._pkd_ax[col]
            stop = self._pkd_ax[col+1]
            for i,r in enumerate(self._unpkd_ax[start:stop]):
                if r == row:
                    return (start+i, col, start+i)

        elif self._order == "coo":
            # O(N) naive... but likely not a major use case
            idx = 0
            for (r,c) in izip(self._coo_rows, self._coo_cols):
                if r == row and c == col:
                    return (idx, idx, idx)
                idx += 1
        else:
            raise ValueError, "Unknown matrix type: %s" % self._order

        return (None, None, None)
    
    def erase(self, row, col):
        """Deletes the item at row,col"""
        #self._update_internal_indices((row,col), 0)
        #self._data.erase(row, col)
        raise NotImplementedError

    def copy(self):
        """Return a copy of self"""
        new_self = self.__class__(*self.shape, dtype=self.dtype)
        new_self._coo_rows = self._coo_rows[:]
        new_self._coo_cols = self._coo_cols[:]
        new_self._coo_values = self._coo_values[:]
        new_self._pkd_ax = self._pkd_ax.copy()
        new_self._unpkd_ax = self._unpkd_ax.copy()
        new_self._values = self._values.copy()
        new_self._order = self._order[:]
        return new_self

    def __eq__(self, other):
        """Returns true if both CSMats are the same"""
        if self.shape != other.shape:
            return False

        if self.hasUpdates():
            self.absorbUpdates()
        if other.hasUpdates():
            self.absorbUpdates()

        if self.shape[1] == 1:
            self.convert("csc")
            other.convert("csc")
        else:
            if self._order is "coo":
                self.convert("csr")

            if other._order is "coo":
                other.convert("csr")
            else:
                self.convert("csr")
    
        if len(self._pkd_ax) != len(other._pkd_ax):
            return False

        if len(self._unpkd_ax) != len(other._unpkd_ax):
            return False

        if (self._pkd_ax != other._pkd_ax).any():
            return False

        if (self._unpkd_ax != other._unpkd_ax).any():
            return False
        
        if (self._values != other._values).any():
            return False
        
        return True
   
    def __str__(self):
        """dump priv data"""
        l = []
        l.append(self._order)
        l.append("_coo_values\t" + '\t'.join(map(str, self._coo_values)))
        l.append("_coo_rows\t" + '\t'.join(map(str, self._coo_rows)))
        l.append("_coo_cols\t" + '\t'.join(map(str, self._coo_cols)))
        l.append("_values\t" + '\t'.join(map(str, self._values)))
        l.append("_pkd_ax\t" + '\t'.join(map(str, self._pkd_ax)))
        l.append("_unpkd_ax\t" + '\t'.join(map(str, self._unpkd_ax)))
        return '\n'.join(l)

    def __ne__(self, other):
        """Return true if both CSMats are not equal"""
        return not (self == other)
           
    def __setitem__(self,args,value):
        """Wrap setitem, complain if out of bounds"""
        try:
            row,col = args
        except:
            # fast support foo[5] = 10, like numpy 1d vectors
            col = args
            row = 0
            args = (row,col)
        
        if row >= self.shape[0]:
            raise IndexError, "Row %d is out of bounds!" % row
        if col >= self.shape[1]:
            raise IndexError, "Col %d is out of bounds!" % col

        if value == 0:
            if args in self:
                self.erase(row, col)
            else:
                return
        else:
            res = self._getitem(args)
            if res == (None, None, None):
                self._coo_rows.append(row)
                self._coo_cols.append(col)
                self._coo_values.append(value)
            else:
                if self._order == "coo":
                    self._coo_values[res[0]] = value
                else:
                    self._values[res[-1]] = value

    def __getitem__(self,args):
        """Wrap getitem to handle slices"""
        try:
            row,col = args
        except TypeError:
            raise IndexError, "Must specify (row, col)"

        if isinstance(row, slice): 
            if row.start is None and row.stop is None:
                return self.getCol(col)
            else:
                raise AttributeError, "Can only handle full : slices per axis"
        elif isinstance(col, slice):
            if col.start is None and col.stop is None:
                return self.getRow(row)
            else:
                raise AttributeError, "Can only handle full : slices per axis"
        else:
            if row >= self.shape[0] or row < 0:
                raise IndexError, "Row out of bounds!"
            if col >= self.shape[1] or col < 0:
                raise IndexError, "Col out of bounds!"

            res = self._getitem(args)
            if res == (None,None,None):
                return self.dtype(0)
            else:
                if self._order == 'coo':
                    return self._coo_values[res[0]]
                else:
                    return self._values[res[-1]]
                
        return self.dtype(0)

    def getRow(self, row):
        """Returns a row in Sparse COO form"""
        if row >= self.shape[0] or row < 0:
            raise IndexError, "Row %d is out of bounds!" % row
        
        if self._order != "csr":
            self.convert("csr")
        
        n_rows,n_cols = self.shape
        v = self.__class__(1, n_cols, dtype=self.dtype)
        
        start = self._pkd_ax[row]
        stop = self._pkd_ax[row + 1]
        n_vals = stop - start
        
        v._coo_rows = [uint32(0)] * n_vals
        v._coo_cols = list(self._unpkd_ax[start:stop])
        v._coo_values = list(self._values[start:stop])
        
        return v

    def getCol(self, col):
        """Return a col in CSMat form"""
        if col >= self.shape[1] or col < 0:
            raise IndexError, "Col %d is out of bounds!" % col
        
        if self._order != "csc":
            self.convert("csc")
        
        n_rows,n_cols = self.shape
        v = self.__class__(n_rows, 1, dtype=self.dtype)
        
        start = self._pkd_ax[col]
        stop = self._pkd_ax[col + 1]
        n_vals = stop - start

        v._coo_cols = [uint32(0)] * n_vals
        v._coo_rows = list(self._unpkd_ax[start:stop])
        v._coo_values = list(self._values[start:stop])
        
        return v

    def transpose(self):
        """Transpose self"""
        new_self = self.copy()

        if new_self._order != "coo":
            rebuild = new_self._order
            new_self.convert("coo")
        else:
            rebuild = None

        new_self.shape = new_self.shape[::-1]
        tmp = new_self._coo_rows
        new_self._coo_rows = new_self._coo_cols
        new_self._coo_cols = tmp

        if rebuild is not None:
            self.convert(rebuild)

        return new_self

    T = property(transpose)

def to_csmat(values, transpose=False, dtype=float):
    """Tries to returns a populated CSMat object

    NOTE: assumes the max value observed in row and col defines the size of the
    matrix
    """
    # if it is a vector
    if isinstance(values, ndarray) and len(values.shape) == 1:
        if transpose:
            mat = nparray_to_csmat(values[:,newaxis], dtype)
        else:
            mat = nparray_to_csmat(values, dtype)
        return mat
    # the empty list
    elif isinstance(values, list) and len(values) == 0:
        mat = CSMat(0,0)
        return mat
    # list of np vectors
    elif isinstance(values, list) and isinstance(values[0], ndarray):
        mat = list_nparray_to_csmat(values, dtype)
        if transpose:
            mat = mat.T
        return mat
    # list of dicts, each representing a row in row order
    elif isinstance(values, list) and isinstance(values[0], dict):
        mat = list_dict_to_csmat(values, dtype)
        if transpose:
            mat = mat.T
        return mat
    # list of csmat, each representing a row in row order
    elif isinstance(values, list) and isinstance(values[0], CSMat):
        mat = list_csmat_to_csmat(values,dtype)
        if transpose:
            mat = mat.T
        return mat
    elif isinstance(values, dict):
        mat = dict_to_csmat(values, dtype)
        if transpose:
            mat = mat.T
        return mat
    elif isinstance(values, CSMat):
        mat = values
        if transpose:
            mat = mat.T
        return mat
    else:
        raise TableException, "Unknown input type"
        
def list_list_to_csmat(data, dtype=float, shape=None):
    """Convert a list of lists into a CSMat

    [[row, col, value], ...]
    """
    rows, cols, values = zip(*data)
    n_rows = max(rows) + 1
    n_cols = max(cols) + 1
    mat = CSMat(n_rows, n_cols)
    mat.bulkCOOUpdate(rows, cols, values)
    return mat

def nparray_to_csmat(data, dtype=float):
    """Convert a numpy array to a CSMat"""
    if len(data.shape) == 1:
        mat = CSMat(1, data.shape[0], dtype=dtype)
        for col_idx, val in enumerate(data):
            mat[(0,col_idx)] = val
    else:
        mat = CSMat(*data.shape, dtype=dtype)
        for row_idx, row in enumerate(data):
            for col_idx, value in enumerate(row):
                mat[(row_idx,col_idx)] = value
    return mat

def list_nparray_to_csmat(data, dtype=float):
    """Takes a list of numpy arrays and creates a csmat"""
    mat = CSMat(len(data), len(data[0]),dtype=dtype)
    rows = []
    cols = []
    values = []
    for row_idx, row in enumerate(data):
        if len(row.shape) != 1:
            raise TableException, "Cannot convert non-1d vectors!"
        if len(row) != mat.shape[1]:
            raise TableException, "Row vector isn't the correct length!"

        for col_idx, val in enumerate(row):
            mat[(row_idx, col_idx)] = val
    return mat

def list_csmat_to_csmat(data, dtype=float):
    """Takes a list of CSMats and creates a CSMat"""
    if isinstance(data[0], CSMat):
        if data[0].shape[0] > data[0].shape[1]:
            is_col = True
            n_cols = len(data)
            n_rows = data[0].shape[0]
        else:
            is_col = False
            n_rows = len(data)
            n_cols = data[0].shape[1]
    else:
        all_keys = flatten([d.keys() for d in data])
        n_rows = max(all_keys, key=itemgetter(0))[0] + 1
        n_cols = max(all_keys, key=itemgetter(1))[1] + 1
        if n_rows > n_cols:
            is_col = True
            n_cols = len(data)
        else:
            is_col = False
            n_rows = len(data)

    mat = CSMat(n_rows, n_cols, dtype=dtype)
    for row_idx,row in enumerate(data):
        for (foo,col_idx),val in row.items():
            if is_col:
                # transpose
                mat[(foo,row_idx)] = val
            else:
                mat[(row_idx,col_idx)] = val
    
    return mat
    
def list_dict_to_csmat(data, dtype=float):
    """Takes a list of dict {(0,col):val} and creates a CSMat"""
    if isinstance(data[0], CSMat):
        if data[0].shape[0] > data[0].shape[1]:
            is_col = True
            n_cols = len(data)
            n_rows = data[0].shape[0]
        else:
            is_col = False
            n_rows = len(data)
            n_cols = data[0].shape[1]
    else:
        all_keys = flatten([d.keys() for d in data])
        n_rows = max(all_keys, key=itemgetter(0))[0] + 1
        n_cols = max(all_keys, key=itemgetter(1))[1] + 1
        if n_rows > n_cols:
            is_col = True
            n_cols = len(data)
        else:
            is_col = False
            n_rows = len(data)

    mat = CSMat(n_rows, n_cols, dtype=dtype)
    for row_idx,row in enumerate(data):
        for (foo,col_idx),val in row.items():
            if is_col:
                # transpose
                mat[(foo,row_idx)] = val
            else:
                mat[(row_idx, col_idx)] = val
    
    return mat

def dict_to_csmat(data, dtype=float):
    """takes a dict {(row,col):val} and creates a CSMat"""
    n_rows = max(data.keys(), key=itemgetter(0))[0] + 1
    n_cols = max(data.keys(), key=itemgetter(1))[1] + 1
    mat = CSMat(n_rows, n_cols,dtype=dtype)

    for (r,c),v in data.items():
        mat[(r,c)] = v
    return mat
