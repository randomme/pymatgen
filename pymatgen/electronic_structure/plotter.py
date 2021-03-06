# coding: utf-8
# Copyright (c) Pymatgen Development Team.
# Distributed under the terms of the MIT License.

from __future__ import division, unicode_literals, print_function
import logging
import math
import itertools
import warnings
from collections import OrderedDict

import numpy as np

from monty.json import jsanitize

from pymatgen import Element
from pymatgen.electronic_structure.core import Spin, OrbitalType
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.util.plotting_utils import get_publication_quality_plot, \
    add_fig_kwargs, get_ax3d_fig_plt

from pymatgen.core.units import Energy
from pymatgen.electronic_structure.boltztrap import BoltztrapError
from pymatgen.symmetry.bandstructure import HighSymmKpath

"""
This module implements plotter for DOS and band structure.
"""

__author__ = "Shyue Ping Ong, Geoffroy Hautier, Anubhav Jain"
__copyright__ = "Copyright 2012, The Materials Project"
__version__ = "0.1"
__maintainer__ = "Shyue Ping Ong"
__email__ = "shyuep@gmail.com"
__date__ = "May 1, 2012"


logger = logging.getLogger(__name__)


class DosPlotter(object):
    """
    Class for plotting DOSs. Note that the interface is extremely flexible
    given that there are many different ways in which people want to view
    DOS. The typical usage is::

        # Initializes plotter with some optional args. Defaults are usually
        # fine,
        plotter = DosPlotter()

        # Adds a DOS with a label.
        plotter.add_dos("Total DOS", dos)

        # Alternatively, you can add a dict of DOSs. This is the typical
        # form returned by CompleteDos.get_spd/element/others_dos().
        plotter.add_dos_dict({"dos1": dos1, "dos2": dos2})
        plotter.add_dos_dict(complete_dos.get_spd_dos())

    Args:
        zero_at_efermi: Whether to shift all Dos to have zero energy at the
            fermi energy. Defaults to True.
        stack: Whether to plot the DOS as a stacked area graph
        key_sort_func: function used to sort the dos_dict keys.
        sigma: A float specifying a standard deviation for Gaussian smearing
            the DOS for nicer looking plots. Defaults to None for no
            smearing.
    """

    def __init__(self, zero_at_efermi=True, stack=False, sigma=None):
        self.zero_at_efermi = zero_at_efermi
        self.stack = stack
        self.sigma = sigma
        self._doses = OrderedDict()

    def add_dos(self, label, dos):
        """
        Adds a dos for plotting.

        Args:
            label:
                label for the DOS. Must be unique.
            dos:
                Dos object
        """
        energies = dos.energies - dos.efermi if self.zero_at_efermi \
            else dos.energies
        densities = dos.get_smeared_densities(self.sigma) if self.sigma \
            else dos.densities
        efermi = dos.efermi
        self._doses[label] = {'energies': energies, 'densities': densities,
                              'efermi': efermi}

    def add_dos_dict(self, dos_dict, key_sort_func=None):
        """
        Add a dictionary of doses, with an optional sorting function for the
        keys.

        Args:
            dos_dict: dict of {label: Dos}
            key_sort_func: function used to sort the dos_dict keys.
        """
        if key_sort_func:
            keys = sorted(dos_dict.keys(), key=key_sort_func)
        else:
            keys = dos_dict.keys()
        for label in keys:
            self.add_dos(label, dos_dict[label])

    def get_dos_dict(self):
        """
        Returns the added doses as a json-serializable dict. Note that if you
        have specified smearing for the DOS plot, the densities returned will
        be the smeared densities, not the original densities.

        Returns:
            Dict of dos data. Generally of the form, {label: {'energies':..,
            'densities': {'up':...}, 'efermi':efermi}}
        """
        return jsanitize(self._doses)

    def get_plot(self, xlim=None, ylim=None):
        """
        Get a matplotlib plot showing the DOS.

        Args:
            xlim: Specifies the x-axis limits. Set to None for automatic
                determination.
            ylim: Specifies the y-axis limits.
        """


        ncolors = max(3, len(self._doses))
        ncolors = min(9, ncolors)

        import palettable

        colors = palettable.colorbrewer.qualitative.Set1_9.mpl_colors

        y = None
        alldensities = []
        allenergies = []
        plt = get_publication_quality_plot(12, 8)

        # Note that this complicated processing of energies is to allow for
        # stacked plots in matplotlib.
        for key, dos in self._doses.items():
            energies = dos['energies']
            densities = dos['densities']
            if not y:
                y = {Spin.up: np.zeros(energies.shape),
                     Spin.down: np.zeros(energies.shape)}
            newdens = {}
            for spin in [Spin.up, Spin.down]:
                if spin in densities:
                    if self.stack:
                        y[spin] += densities[spin]
                        newdens[spin] = y[spin].copy()
                    else:
                        newdens[spin] = densities[spin]
            allenergies.append(energies)
            alldensities.append(newdens)

        keys = list(self._doses.keys())
        keys.reverse()
        alldensities.reverse()
        allenergies.reverse()
        allpts = []
        for i, key in enumerate(keys):
            x = []
            y = []
            for spin in [Spin.up, Spin.down]:
                if spin in alldensities[i]:
                    densities = list(int(spin) * alldensities[i][spin])
                    energies = list(allenergies[i])
                    if spin == Spin.down:
                        energies.reverse()
                        densities.reverse()
                    x.extend(energies)
                    y.extend(densities)
            allpts.extend(list(zip(x, y)))
            if self.stack:
                plt.fill(x, y, color=colors[i % ncolors],
                         label=str(key))
            else:
                plt.plot(x, y, color=colors[i % ncolors],
                         label=str(key), linewidth=3)
            if not self.zero_at_efermi:
                ylim = plt.ylim()
                plt.plot([self._doses[key]['efermi'],
                          self._doses[key]['efermi']], ylim,
                         color=colors[i % ncolors],
                         linestyle='--', linewidth=2)

        if xlim:
            plt.xlim(xlim)
        if ylim:
            plt.ylim(ylim)
        else:
            xlim = plt.xlim()
            relevanty = [p[1] for p in allpts
                         if xlim[0] < p[0] < xlim[1]]
            plt.ylim((min(relevanty), max(relevanty)))

        if self.zero_at_efermi:
            ylim = plt.ylim()
            plt.plot([0, 0], ylim, 'k--', linewidth=2)

        plt.xlabel('Energies (eV)')
        plt.ylabel('Density of states')

        plt.legend()
        leg = plt.gca().get_legend()
        ltext = leg.get_texts()  # all the text.Text instance in the legend
        plt.setp(ltext, fontsize=30)
        plt.tight_layout()
        return plt

    def save_plot(self, filename, img_format="eps", xlim=None, ylim=None):
        """
        Save matplotlib plot to a file.

        Args:
            filename: Filename to write to.
            img_format: Image format to use. Defaults to EPS.
            xlim: Specifies the x-axis limits. Set to None for automatic
                determination.
            ylim: Specifies the y-axis limits.
        """
        plt = self.get_plot(xlim, ylim)
        plt.savefig(filename, format=img_format)

    def show(self, xlim=None, ylim=None):
        """
        Show the plot using matplotlib.

        Args:
            xlim: Specifies the x-axis limits. Set to None for automatic
                determination.
            ylim: Specifies the y-axis limits.
        """
        plt = self.get_plot(xlim, ylim)
        plt.show()


class BSPlotter(object):
    """
    Class to plot or get data to facilitate the plot of band structure objects.

    Args:
        bs: A BandStructureSymmLine object.
    """

    def __init__(self, bs):
        if not isinstance(bs, BandStructureSymmLine):
            raise ValueError(
                "BSPlotter only works with BandStructureSymmLine objects. "
                "A BandStructure object (on a uniform grid for instance and "
                "not along symmetry lines won't work)")
        self._bs = bs
        # TODO: come with an intelligent way to cut the highest unconverged
        # bands
        self._nb_bands = self._bs.nb_bands

    def _maketicks(self, plt):
        """
        utility private method to add ticks to a band structure
        """
        ticks = self.get_ticks()
        # Sanitize only plot the uniq values
        uniq_d = []
        uniq_l = []
        temp_ticks = list(zip(ticks['distance'], ticks['label']))
        for i in range(len(temp_ticks)):
            if i == 0:
                uniq_d.append(temp_ticks[i][0])
                uniq_l.append(temp_ticks[i][1])
                logger.debug("Adding label {l} at {d}".format(
                    l=temp_ticks[i][0], d=temp_ticks[i][1]))
            else:
                if temp_ticks[i][1] == temp_ticks[i - 1][1]:
                    logger.debug("Skipping label {i}".format(
                        i=temp_ticks[i][1]))
                else:
                    logger.debug("Adding label {l} at {d}".format(
                        l=temp_ticks[i][0], d=temp_ticks[i][1]))
                    uniq_d.append(temp_ticks[i][0])
                    uniq_l.append(temp_ticks[i][1])

        logger.debug("Unique labels are %s" % list(zip(uniq_d, uniq_l)))
        plt.gca().set_xticks(uniq_d)
        plt.gca().set_xticklabels(uniq_l)

        for i in range(len(ticks['label'])):
            if ticks['label'][i] is not None:
                # don't print the same label twice
                if i != 0:
                    if ticks['label'][i] == ticks['label'][i - 1]:
                        logger.debug("already print label... "
                                     "skipping label {i}".format(
                            i=ticks['label'][i]))
                    else:
                        logger.debug("Adding a line at {d}"
                                     " for label {l}".format(
                            d=ticks['distance'][i], l=ticks['label'][i]))
                        plt.axvline(ticks['distance'][i], color='k')
                else:
                    logger.debug("Adding a line at {d} for label {l}".format(
                        d=ticks['distance'][i], l=ticks['label'][i]))
                    plt.axvline(ticks['distance'][i], color='k')
        return plt

    def bs_plot_data(self, zero_to_efermi=True):

        """
        Get the data nicely formatted for a plot

        Args:
            zero_to_efermi: Automatically subtract off the Fermi energy from the
                eigenvalues and plot.

        Returns:
            A dict of the following format:
            ticks: A dict with the 'distances' at which there is a kpoint (the
            x axis) and the labels (None if no label)
            energy: A dict storing bands for spin up and spin down data
            [{Spin:[band_index][k_point_index]}] as a list (one element
            for each branch) of energy for each kpoint. The data is
            stored by branch to facilitate the plotting
            vbm: A list of tuples (distance,energy) marking the vbms. The
            energies are shifted with respect to the fermi level is the
            option has been selected.
            cbm: A list of tuples (distance,energy) marking the cbms. The
            energies are shifted with respect to the fermi level is the
            option has been selected.
            lattice: The reciprocal lattice.
            zero_energy: This is the energy used as zero for the plot.
            band_gap:A string indicating the band gap and its nature (empty if
            it's a metal).
            is_metal: True if the band structure is metallic (i.e., there is at
            least one band crossing the fermi level).
        """
        distance = []
        energy = []
        if self._bs.is_metal():
            zero_energy = self._bs.efermi
        else:
            zero_energy = self._bs.get_vbm()['energy']

        if not zero_to_efermi:
            zero_energy = 0.0

        for b in self._bs.branches:

            if self._bs.is_spin_polarized:
                energy.append({str(Spin.up): [], str(Spin.down): []})
            else:
                energy.append({str(Spin.up): []})
            distance.append([self._bs.distance[j]
                             for j in range(b['start_index'],
                                            b['end_index'] + 1)])
            ticks = self.get_ticks()

            for i in range(self._nb_bands):
                energy[-1][str(Spin.up)].append(
                    [self._bs.bands[Spin.up][i][j] - zero_energy
                     for j in range(b['start_index'], b['end_index'] + 1)])
            if self._bs.is_spin_polarized:
                for i in range(self._nb_bands):
                    energy[-1][str(Spin.down)].append(
                        [self._bs.bands[Spin.down][i][j] - zero_energy
                         for j in range(b['start_index'], b['end_index'] + 1)])

        vbm = self._bs.get_vbm()
        cbm = self._bs.get_cbm()

        vbm_plot = []
        cbm_plot = []

        for index in cbm['kpoint_index']:
            cbm_plot.append((self._bs.distance[index],
                             cbm['energy'] - zero_energy if zero_to_efermi
                             else cbm['energy']))

        for index in vbm['kpoint_index']:
            vbm_plot.append((self._bs.distance[index],
                             vbm['energy'] - zero_energy if zero_to_efermi
                             else vbm['energy']))

        bg = self._bs.get_band_gap()
        direct = "Indirect"
        if bg['direct']:
            direct = "Direct"

        return {'ticks': ticks, 'distances': distance, 'energy': energy,
                'vbm': vbm_plot, 'cbm': cbm_plot,
                'lattice': self._bs.lattice_rec.as_dict(),
                'zero_energy': zero_energy, 'is_metal': self._bs.is_metal(),
                'band_gap': "{} {} bandgap = {}".format(direct,
                                                        bg['transition'],
                                                        bg['energy'])
                if not self._bs.is_metal() else ""}

    def get_plot(self, zero_to_efermi=True, ylim=None, smooth=False,
                 vbm_cbm_marker=False,smooth_tol=None):
        """
        Get a matplotlib object for the bandstructure plot.
        Blue lines are up spin, red lines are down
        spin.

        Args:
            zero_to_efermi: Automatically subtract off the Fermi energy from
                the eigenvalues and plot (E-Ef).
            ylim: Specify the y-axis (energy) limits; by default None let
                the code choose. It is vbm-4 and cbm+4 if insulator
                efermi-10 and efermi+10 if metal
            smooth: interpolates the bands by a spline cubic
            smooth_tol (float) : tolerance for fitting spline to band data.
                Default is None such that no tolerance will be used.
        """
        plt = get_publication_quality_plot(12, 8)
        from matplotlib import rc
        import scipy.interpolate as scint
        try:
            rc('text', usetex=True)
        except:
            # Fall back on non Tex if errored.
            rc('text', usetex=False)

        # main internal config options
        e_min = -4
        e_max = 4
        if self._bs.is_metal():
            e_min = -10
            e_max = 10
        #band_linewidth = 3
        band_linewidth = 1

        data = self.bs_plot_data(zero_to_efermi)
        if not smooth:
            for d in range(len(data['distances'])):
                for i in range(self._nb_bands):
                    plt.plot(data['distances'][d],
                             [data['energy'][d][str(Spin.up)][i][j]
                              for j in range(len(data['distances'][d]))], 'b-',
                             linewidth=band_linewidth)
                    if self._bs.is_spin_polarized:
                        plt.plot(data['distances'][d],
                                 [data['energy'][d][str(Spin.down)][i][j]
                                  for j in range(len(data['distances'][d]))],
                                 'r--', linewidth=band_linewidth)
        else:
            # Interpolation failure can be caused by trying to fit an entire
            # band with one spline rather than fitting with piecewise splines
            # (splines are ill-suited to fit discontinuities).
            #
            # The number of splines used to fit a band is determined by the 
            # number of branches (high symmetry lines) defined in the 
            # BandStructureSymmLine object (see BandStructureSymmLine._branches). 
            
            warning = "WARNING! Distance / branch {d}, band {i} cannot be "+\
                      "interpolated.\n"+\
                      "See full warning in source.\n"+\
                      "If this is not a mistake, try increasing "+\
                      "smooth_tol.\nCurrent smooth_tol is {s}."

            for d in range(len(data['distances'])):
                for i in range(self._nb_bands):
                    tck = scint.splrep(
                        data['distances'][d],
                        [data['energy'][d][str(Spin.up)][i][j]
                         for j in range(len(data['distances'][d]))],
                        s = smooth_tol)
                    step = (data['distances'][d][-1]
                            - data['distances'][d][0]) / 1000

                    xs = [x * step + data['distances'][d][0] 
                          for x in range(1000)]

                    ys = [scint.splev(x * step + data['distances'][d][0],
                                      tck, der=0)
                          for x in range(1000)]
                    
                    for y in ys:
                        if np.isnan(y):
                            print(warning.format(d=str(d),i=str(i),
                                                 s=str(smooth_tol)))
                            break

                    plt.plot(xs, ys, 'b-', linewidth=band_linewidth)

                    if self._bs.is_spin_polarized:
                        tck = scint.splrep(
                            data['distances'][d],
                            [data['energy'][d][str(Spin.down)][i][j]
                             for j in range(len(data['distances'][d]))],
                            s = smooth_tol)
                        step = (data['distances'][d][-1]
                                - data['distances'][d][0]) / 1000

                        xs = [x * step + data['distances'][d][0]
                              for x in range(1000)]

                        ys = [scint.splev(
                                 x * step + data['distances'][d][0],
                                 tck, der=0)
                              for x in range(1000)]

                        for y in ys:
                            if np.isnan(y):
                                print(warning.format(d=str(d),i=str(i),
                                                     s=str(smooth_tol)))
                                break

                        plt.plot(xs, ys, 'r--', linewidth=band_linewidth)

#                        plt.plot([x * step + data['distances'][d][0]
#                                  for x in range(1000)],
#                                 [scint.splev(
#                                     x * step + data['distances'][d][0],
#                                     tck, der=0)
#                                  for x in range(1000)], 'r--',
#                                 linewidth=band_linewidth)

        self._maketicks(plt)

        # Main X and Y Labels
        plt.xlabel(r'$\mathrm{Wave\ Vector}$', fontsize=30)
        ylabel = r'$\mathrm{E\ -\ E_f\ (eV)}$' if zero_to_efermi \
            else r'$\mathrm{Energy\ (eV)}$'
        plt.ylabel(ylabel, fontsize=30)

        # Draw Fermi energy, only if not the zero
        if not zero_to_efermi:
            ef = self._bs.efermi
            plt.axhline(ef, linewidth=2, color='k')

        # X range (K)
        # last distance point
        x_max = data['distances'][-1][-1]
        plt.xlim(0, x_max)

        if ylim is None:
            if self._bs.is_metal():
                # Plot A Metal
                if zero_to_efermi:
                    plt.ylim(e_min, e_max)
                else:
                    plt.ylim(self._bs.efermi + e_min, self._bs.efermi + e_max)
            else:
                if vbm_cbm_marker:
                    for cbm in data['cbm']:
                        plt.scatter(cbm[0], cbm[1], color='r', marker='o',
                                    s=100)
                    for vbm in data['vbm']:
                        plt.scatter(vbm[0], vbm[1], color='g', marker='o',
                                    s=100)	
                plt.ylim(data['vbm'][0][1] + e_min,
                         data['cbm'][0][1] + e_max)
        else:
            plt.ylim(ylim)
           
        plt.tight_layout()

        return plt

    def show(self, zero_to_efermi=True, ylim=None, smooth=False, 
             smooth_tol=None):
        """
        Show the plot using matplotlib.

        Args:
            zero_to_efermi: Automatically subtract off the Fermi energy from
                the eigenvalues and plot (E-Ef).
            ylim: Specify the y-axis (energy) limits; by default None let
                the code choose. It is vbm-4 and cbm+4 if insulator
                efermi-10 and efermi+10 if metal
            smooth: interpolates the bands by a spline cubic
            smooth_tol (float) : tolerance for fitting spline to band data.
                Default is None such that no tolerance will be used.
        """
        plt = self.get_plot(zero_to_efermi, ylim, smooth)
        plt.show()

    def save_plot(self, filename, img_format="eps", ylim=None,
                  zero_to_efermi=True, smooth=False):
        """
        Save matplotlib plot to a file.

        Args:
            filename: Filename to write to.
            img_format: Image format to use. Defaults to EPS.
            ylim: Specifies the y-axis limits.
        """
        plt = self.get_plot(ylim=ylim, zero_to_efermi=zero_to_efermi,
                            smooth=smooth)
        plt.savefig(filename, format=img_format)
        plt.close()

    def get_ticks(self):
        """
        Get all ticks and labels for a band structure plot.

        Returns:
            A dict with 'distance': a list of distance at which ticks should
            be set and 'label': a list of label for each of those ticks.
        """
        tick_distance = []
        tick_labels = []
        previous_label = self._bs.kpoints[0].label
        previous_branch = self._bs.branches[0]['name']
        for i, c in enumerate(self._bs.kpoints):
            if c.label is not None:
                tick_distance.append(self._bs.distance[i])
                this_branch = None
                for b in self._bs.branches:
                    if b['start_index'] <= i <= b['end_index']:
                        this_branch = b['name']
                        break
                if c.label != previous_label \
                        and previous_branch != this_branch:
                    label1 = c.label
                    if label1.startswith("\\") or label1.find("_") != -1:
                        label1 = "$" + label1 + "$"
                    label0 = previous_label
                    if label0.startswith("\\") or label0.find("_") != -1:
                        label0 = "$" + label0 + "$"
                    tick_labels.pop()
                    tick_distance.pop()
                    tick_labels.append(label0 + "$\mid$" + label1)
                else:
                    if c.label.startswith("\\") or c.label.find("_") != -1:
                        tick_labels.append("$" + c.label + "$")
                    else:
                        tick_labels.append(c.label)
                previous_label = c.label
                previous_branch = this_branch
        return {'distance': tick_distance, 'label': tick_labels}

    def plot_compare(self, other_plotter):
        """
        plot two band structure for comparison. One is in red the other in blue
        (no difference in spins). The two band structures need to be defined
        on the same symmetry lines! and the distance between symmetry lines is
        the one of the band structure used to build the BSPlotter

        Args:
            another band structure object defined along the same symmetry lines

        Returns:
            a matplotlib object with both band structures

        """
        # TODO: add exception if the band structures are not compatible
        plt = self.get_plot()
        data_orig = self.bs_plot_data()
        data = other_plotter.bs_plot_data()
        band_linewidth = 1
        for i in range(other_plotter._nb_bands):
            for d in range(len(data_orig['distances'])):
                plt.plot(data_orig['distances'][d],
                         [e[str(Spin.up)][i] for e in data['energy']][d],
                         'r-', linewidth=band_linewidth)
        if other_plotter._bs.is_spin_polarized:
            plt.plot(data_orig['distances'],
                     [e for e in data['energy'][i][str(Spin.down)]],
                     'r-', linewidth=band_linewidth)
        return plt

    def plot_brillouin(self):
        """
        plot the Brillouin zone
        """

        # get labels and lines
        labels = {}
        for k in self._bs.kpoints:
            if k.label:
                labels[k.label] = k.frac_coords

        lines = []
        for b in self._bs.branches:
            lines.append([self._bs.kpoints[b['start_index']].frac_coords, self._bs.kpoints[b['end_index']].frac_coords])

        plot_brillouin_zone(self._bs.lattice_rec, lines=lines, labels=labels)


class BSPlotterProjected(BSPlotter):
    """
    Class to plot or get data to facilitate the plot of band structure objects
    projected along orbitals, elements or sites.

    Args:
        bs: A BandStructureSymmLine object with projections.
    """

    def __init__(self, bs):
        if len(bs.projections) == 0:
            raise ValueError("try to plot projections"
                             " on a band structure without any")
        super(BSPlotterProjected, self).__init__(bs)

    def _get_projections_by_branches(self, dictio):
        proj = self._bs.get_projections_on_elements_and_orbitals(dictio)
        proj_br = []
        for b in self._bs.branches:
            if self._bs.is_spin_polarized:
                proj_br.append(
                    {str(Spin.up): [[] for l in range(self._nb_bands)],
                     str(Spin.down): [[] for l in range(self._nb_bands)]})
            else:
                proj_br.append(
                    {str(Spin.up): [[] for l in range(self._nb_bands)]})

            for i in range(self._nb_bands):
                for j in range(b['start_index'], b['end_index'] + 1):
                    proj_br[-1][str(Spin.up)][i].append(
                        {e: {o: proj[Spin.up][i][j][e][o]
                             for o in proj[Spin.up][i][j][e]}
                         for e in proj[Spin.up][i][j]})
            if self._bs.is_spin_polarized:
                for b in self._bs.branches:
                    for i in range(self._nb_bands):
                        for j in range(b['start_index'], b['end_index'] + 1):
                            proj_br[-1][str(Spin.down)][i].append(
                                {e: {o: proj[Spin.down][i][j][e][o]
                                     for o in proj[Spin.down][i][j][e]}
                                 for e in proj[Spin.down][i][j]})
        return proj_br

    def get_projected_plots_dots(self, dictio, zero_to_efermi=True, ylim=None,
                                 vbm_cbm_marker=False):
        """
        Method returning a plot composed of subplots along different elements
        and orbitals.

        Args:
            dictio: The element and orbitals you want a projection on. The
                format is {Element:[Orbitals]} for instance
                {'Cu':['d','s'],'O':['p']} will give projections for Cu on
                d and s orbitals and on oxygen p.

        Returns:
            a pylab object with different subfigures for each projection
            The blue and red colors are for spin up and spin down.
            The bigger the red or blue dot in the band structure the higher
            character for the corresponding element and orbital.
        """
        band_linewidth = 1.0
        fig_number = sum([len(v) for v in dictio.values()])
        proj = self._get_projections_by_branches(dictio)
        data = self.bs_plot_data(zero_to_efermi)
        plt = get_publication_quality_plot(12, 8)
        e_min = -4
        e_max = 4
        if self._bs.is_metal():
            e_min = -10
            e_max = 10
        count = 1

        for el in dictio:
            for o in dictio[el]:
                plt.subplot(100 * math.ceil(fig_number / 2) + 20 + count)
                self._maketicks(plt)
                for b in range(len(data['distances'])):
                    for i in range(self._nb_bands):
                        plt.plot(data['distances'][b],
                                 [data['energy'][b][str(Spin.up)][i][j]
                                  for j in range(len(data['distances'][b]))],
                                 'b-',
                                 linewidth=band_linewidth)
                        if self._bs.is_spin_polarized:
                            plt.plot(data['distances'][b],
                                     [data['energy'][b][str(Spin.down)][i][j]
                                      for j in
                                      range(len(data['distances'][b]))],
                                     'r--', linewidth=band_linewidth)
                            for j in range(
                                    len(data['energy'][b][str(Spin.up)][i])):
                                plt.plot(data['distances'][b][j],
                                         data['energy'][b][str(Spin.down)][i][
                                             j], 'ro',
                                         markersize=
                                         proj[b][str(Spin.down)][i][j][str(el)][
                                             o] * 15.0)
                        for j in range(len(data['energy'][b][str(Spin.up)][i])):
                            plt.plot(data['distances'][b][j],
                                     data['energy'][b][str(Spin.up)][i][j],
                                     'bo',
                                     markersize=
                                     proj[b][str(Spin.up)][i][j][str(el)][
                                         o] * 15.0)
                if ylim is None:
                    if self._bs.is_metal():
                        if zero_to_efermi:
                            plt.ylim(e_min, e_max)
                        else:
                            plt.ylim(self._bs.efermi + e_min, self._bs.efermi
                                     + e_max)
                    else:
                        if vbm_cbm_marker:
                            for cbm in data['cbm']:
                                plt.scatter(cbm[0], cbm[1], color='r',
                                            marker='o',
                                            s=100)

                            for vbm in data['vbm']:
                                plt.scatter(vbm[0], vbm[1], color='g',
                                            marker='o',
                                            s=100)

                        plt.ylim(data['vbm'][0][1] + e_min, data['cbm'][0][1]
                                 + e_max)
                else:
                    plt.ylim(ylim)
                plt.title(str(el) + " " + str(o))
                count += 1
        return plt

    def get_elt_projected_plots(self, zero_to_efermi=True, ylim=None,
                                vbm_cbm_marker=False):
        """
        Method returning a plot composed of subplots along different elements

        Returns:
            a pylab object with different subfigures for each projection
            The blue and red colors are for spin up and spin down
            The bigger the red or blue dot in the band structure the higher
            character for the corresponding element and orbital
        """
        band_linewidth = 1.0
        proj = self._get_projections_by_branches({e.symbol: ['s', 'p', 'd']
                                                  for e in
                                                  self._bs.structure.composition.elements})
        data = self.bs_plot_data(zero_to_efermi)
        plt = get_publication_quality_plot(12, 8)
        e_min = -4
        e_max = 4
        if self._bs.is_metal():
            e_min = -10
            e_max = 10
        count = 1
        for el in self._bs.structure.composition.elements:
            plt.subplot(220 + count)
            self._maketicks(plt)
            for b in range(len(data['distances'])):
                for i in range(self._nb_bands):
                    plt.plot(data['distances'][b],
                             [data['energy'][b][str(Spin.up)][i][j]
                              for j in range(len(data['distances'][b]))], '-', color=[192/255,192/255,192/255],
                             linewidth=band_linewidth)
                    if self._bs.is_spin_polarized:
                        plt.plot(data['distances'][b],
                                 [data['energy'][b][str(Spin.down)][i][j]
                                  for j in range(len(data['distances'][b]))],
                                 '--', color=[128/255,128/255,128/255], linewidth=band_linewidth)
                        for j in range(len(data['energy'][b][str(Spin.up)][i])):
                            markerscale = sum([proj[b][str(Spin.down)][i][
                                                  j][str(el)][o] for o in
                                              proj[b]
                                              [str(Spin.down)][i][j][
                                                  str(el)]])
                            plt.plot(data['distances'][b][j],
                                     data['energy'][b][str(Spin.down)][i][j], 'bo',
                                     markersize=markerscale*15.0,color=[markerscale,0.3*markerscale,0.4*markerscale])
                    for j in range(len(data['energy'][b][str(Spin.up)][i])):
                        markerscale = sum(
                            [proj[b][str(Spin.up)][i][j][str(el)][o]
                             for o in proj[b]
                             [str(Spin.up)][i][j][str(el)]])
                        plt.plot(data['distances'][b][j],
                                 data['energy'][b][str(Spin.up)][i][j], 'o',
                                 markersize=markerscale*15.0, color=[markerscale, 0.3*markerscale, 0.4*markerscale])
            if ylim is None:
                if self._bs.is_metal():
                    if zero_to_efermi:
                        plt.ylim(e_min, e_max)
                    else:
                        plt.ylim(self._bs.efermi + e_min, self._bs.efermi
                                 + e_max)
                else:
                    if vbm_cbm_marker:
                        for cbm in data['cbm']:
                            plt.scatter(cbm[0], cbm[1], color='r', marker='o',
                                        s=100)

                        for vbm in data['vbm']:
                            plt.scatter(vbm[0], vbm[1], color='g', marker='o',
                                        s=100)

                    plt.ylim(data['vbm'][0][1] + e_min, data['cbm'][0][1]
                             + e_max)
            else:
                plt.ylim(ylim)
            plt.title(str(el))
            count += 1

        return plt

    def get_elt_projected_plots_color(self, zero_to_efermi=True,
                                      elt_ordered=None):
        """
        returns a pylab plot object with one plot where the band structure
        line color depends on the character of the band (along different
        elements). Each element is associated with red, green or blue
        and the corresponding rgb color depending on the character of the band
        is used. The method can only deal with binary and ternary compounds

        spin up and spin down are differientiated by a '-' and a '--' line

        Args:
            elt_ordered: A list of Element ordered. The first one is red,
                second green, last blue

        Returns:
            a pylab object

        """
        band_linewidth = 3.0
        if len(self._bs.structure.composition.elements) > 3:
            raise ValueError
        if elt_ordered is None:
            elt_ordered = self._bs.structure.composition.elements
        proj = self._get_projections_by_branches(
            {e.symbol: ['s', 'p', 'd']
             for e in self._bs.structure.composition.elements})
        data = self.bs_plot_data(zero_to_efermi)
        plt = get_publication_quality_plot(12, 8)

        spins = [Spin.up]
        if self._bs.is_spin_polarized:
            spins = [Spin.up, Spin.down]
        self._maketicks(plt)
        for s in spins:
            for b in range(len(data['distances'])):
                for i in range(self._nb_bands):
                    for j in range(len(data['energy'][b][str(s)][i]) - 1):
                        sum_e = 0.0
                        for el in elt_ordered:
                            sum_e = sum_e + \
                                    sum([proj[b][str(s)][i][j][str(el)][o]
                                         for o
                                         in proj[b][str(s)][i][j][str(el)]])
                        if sum_e == 0.0:
                            color = [0.0] * len(elt_ordered)
                        else:
                            color = [sum([proj[b][str(s)][i][j][str(el)][o]
                                          for o
                                          in proj[b][str(s)][i][j][str(el)]])
                                     / sum_e
                                     for el in elt_ordered]
                        if len(color) == 2:
                            color.append(0.0)
                            color[2] = color[1]
                            color[1] = 0.0
                        sign = '-'
                        if s == Spin.down:
                            sign = '--'
                        plt.plot([data['distances'][b][j],
                                  data['distances'][b][j + 1]],
                                 [data['energy'][b][str(s)][i][j],
                                  data['energy'][b][str(s)][i][j + 1]], sign,
                                 color=color, linewidth=band_linewidth)

        if self._bs.is_metal():
            if zero_to_efermi:
                e_min = -10
                e_max = 10
                plt.ylim(e_min, e_max)
                plt.ylim(self._bs.efermi + e_min, self._bs.efermi + e_max)
        else:
            plt.ylim(data['vbm'][0][1] - 4.0, data['cbm'][0][1] + 2.0)
        return plt


class BSDOSPlotter():
    """
    A joint, aligned band structure and density of states plot. Contributions from Jan Pohls
    as well as the online example from Germain Salvato-Vallverdu:
    http://gvallver.perso.univ-pau.fr/?p=587
    """

    def __init__(self, bs_projection="elements", dos_projection="elements",
                 vb_energy_range=4, cb_energy_range=4, fixed_cb_energy=False,
                 egrid_interval=1, font="Times New Roman", axis_fontsize=20,
                 tick_fontsize=15, legend_fontsize=14, bs_legend="best",
                 dos_legend="best"):

        """
        Instantiate plotter settings.

        Args:
            bs_projection (str): "elements" or None
            dos_projection (str): "elements", "orbitals", or None
            vb_energy_range (float): energy in eV to show of valence bands
            cb_energy_range (float): energy in eV to show of conduction bands
            fixed_cb_energy (bool): If true, the cb_energy_range will be interpreted
                as constant (i.e., no gap correction for cb energy)
            egrid_interval (float): interval for grid marks
            font (str): font family
            axis_fontsize (float): font size for axis
            tick_fontsize (float): font size for axis tick labels
            legend_fontsize (float): font size for legends
            bs_legend (str): matplotlib string location for legend or None
            dos_legend (str): matplotlib string location for legend or None
        """
        self.bs_projection = bs_projection
        self.dos_projection = dos_projection
        self.vb_energy_range = vb_energy_range
        self.cb_energy_range = cb_energy_range
        self.fixed_cb_energy = fixed_cb_energy
        self.egrid_interval = egrid_interval
        self.font = font
        self.axis_fontsize = axis_fontsize
        self.tick_fontsize = tick_fontsize
        self.legend_fontsize = legend_fontsize
        self.bs_legend = bs_legend
        self.dos_legend = dos_legend

    def get_plot(self, bs, dos):
        """
        Get a matplotlib plot object.
        Args:
            bs (BandStructure): the bandstructure to plot. Projection data must exist for projected plots.
            dos (Dos): the Dos to plot. Projection data must exist (i.e., CompleteDos) for projected plots.

        Returns:
            a matplotlib plt object on which you can call commands like show() and savefig()

        """
        import matplotlib.lines as mlines
        from matplotlib.gridspec import GridSpec
        import matplotlib.pyplot as mplt

        # make sure the user-specified band structure projection is valid
        elements = [e.symbol for e in dos.structure.composition.elements]
        bs_projection = self.bs_projection

        if bs_projection and bs_projection.lower() == "elements" and \
                (len(elements) not in [2, 3] or not bs.get_projection_on_elements()):
            warnings.warn("Cannot get element projected data; either the projection data "
                          "doesn't exist, or you don't have a compound with exactly 2 or 3"
                          " unique elements.")
            bs_projection = None

        # specify energy range of plot
        emin = -self.vb_energy_range
        emax = self.cb_energy_range if self.fixed_cb_energy else \
            self.cb_energy_range + bs.get_band_gap()["energy"]

        # initialize all the k-point labels and k-point x-distances for bs plot
        xlabels = []  # all symmetry point labels on x-axis
        xlabel_distances = []  # positions of symmetry point x-labels
        x_distances = []  # x positions of kpoint data
        prev_right_klabel = None  # used to determine which branches require a midline separator

        for idx, l in enumerate(bs.branches):
            # get left and right kpoint labels of this branch
            left_k, right_k = l["name"].split("-")

            # add $ notation for LaTeX kpoint labels
            if left_k[0] == "\\" or "_" in left_k:
                left_k = "$"+left_k+"$"
            if right_k[0] == "\\" or "_" in right_k:
                right_k = "$"+right_k+"$"

            # add left k label to list of labels
            if prev_right_klabel is None:
                xlabels.append(left_k)
                xlabel_distances.append(0)
            elif prev_right_klabel != left_k:  # used for pipe separator
                xlabels[-1] = xlabels[-1]+ "$\\mid$ " + left_k

            # add right k label to list of labels
            xlabels.append(right_k)
            prev_right_klabel = right_k

            # add x-coordinates for labels
            left_kpoint = bs.kpoints[l["start_index"]].cart_coords
            right_kpoint = bs.kpoints[l["end_index"]].cart_coords
            distance = np.linalg.norm(right_kpoint - left_kpoint)
            xlabel_distances.append(xlabel_distances[-1] + distance)

            # add x-coordinates for kpoint data
            npts = l["end_index"] - l["start_index"]
            distance_interval = distance/npts
            x_distances.append(xlabel_distances[-2])
            for i in range(npts):
                x_distances.append(x_distances[-1] + distance_interval)

        # set up bs and dos plot
        gs = GridSpec(1, 2, width_ratios=[2, 1])
        fig = mplt.figure(figsize=(11, 8.5))
        fig.patch.set_facecolor('white')
        bs_ax = mplt.subplot(gs[0])
        dos_ax = mplt.subplot(gs[1])

        # set basic axes limits for the plot
        bs_ax.set_xlim(0, x_distances[-1])
        bs_ax.set_ylim(emin, emax)
        dos_ax.set_ylim(emin, emax)

        # add BS xticks, labels, etc.
        bs_ax.set_xticks(xlabel_distances)
        bs_ax.set_xticklabels(xlabels, size=self.tick_fontsize)
        bs_ax.set_xlabel('Wavevector $k$', fontsize=self.axis_fontsize, family=self.font)
        bs_ax.set_ylabel('$E-E_F$ / eV', fontsize=self.axis_fontsize, family=self.font)

        # add BS fermi level line at E=0 and gridlines
        bs_ax.hlines(y=0, xmin=0, xmax=x_distances[-1], color="k", lw=2)
        bs_ax.set_yticks(np.arange(emin, emax+1E-5, self.egrid_interval))
        bs_ax.set_yticklabels(np.arange(emin, emax+1E-5, self.egrid_interval),
                              size=self.tick_fontsize)
        dos_ax.set_yticks(np.arange(emin, emax+1E-5, self.egrid_interval))
        bs_ax.grid(color=[0.5, 0.5, 0.5], linestyle='dotted', linewidth=1)
        dos_ax.set_yticklabels([])
        dos_ax.grid(color=[0.5, 0.5, 0.5], linestyle='dotted', linewidth=1)

        # renormalize the band energy to the Fermi level
        band_energies = {}
        for spin in (Spin.up, Spin.down):
            if spin in bs.bands:
                band_energies[spin] = []
                for band in bs.bands[spin]:
                    band_energies[spin].append([e - bs.efermi for e in band])

        # renormalize the DOS energies to Fermi level
        dos_energies = [e - dos.efermi for e in dos.energies]

        # get the projection data to set colors for the band structure
        colordata = self._get_colordata(bs, elements, bs_projection)

        # plot the colored band structure lines
        for spin in (Spin.up, Spin.down):
            if spin in band_energies:
                linestyles = "solid" if spin == Spin.up else "dotted"
                for band_idx, band in enumerate(band_energies[spin]):
                    self._rgbline(bs_ax, x_distances, band,
                                  colordata[spin][band_idx, :, 0],
                                  colordata[spin][band_idx, :, 1],
                                  colordata[spin][band_idx, :, 2],
                                  linestyles=linestyles)

        # Plot the DOS and projected DOS
        for spin in (Spin.up, Spin.down):
            if spin in dos.densities:
                # plot the total DOS
                dos_densities = dos.densities[spin] * int(spin)
                label = "total" if spin == Spin.up else None
                dos_ax.plot(dos_densities, dos_energies, color=(0.6, 0.6, 0.6),
                            label=label)
                dos_ax.fill_between(dos_densities, 0, dos_energies,
                                    color=(0.7, 0.7, 0.7),
                                    facecolor=(0.7, 0.7, 0.7))

                # plot the atom-projected DOS
                if self.dos_projection.lower() == "elements":
                    colors = ['b', 'r', 'g', 'm', 'y', 'c', 'k', 'w']
                    el_dos = dos.get_element_dos()
                    for idx, el in enumerate(elements):
                        dos_densities = el_dos[Element(el)].densities[spin] *\
                                        int(spin)
                        label = el if spin == Spin.up else None
                        dos_ax.plot(dos_densities, dos_energies,
                                    color=colors[idx], label=label)

                elif self.dos_projection.lower() == "orbitals":
                    # plot each of the atomic projected DOS
                    colors = ['b', 'r', 'g', 'm']
                    spd_dos = dos.get_spd_dos()
                    for idx, orb in enumerate([OrbitalType.s, OrbitalType.p,
                                               OrbitalType.d, OrbitalType.f]):
                        if orb in spd_dos:
                            dos_densities = spd_dos[orb].densities[spin] *\
                                            int(spin)
                            label = orb if spin == Spin.up else None
                            dos_ax.plot(dos_densities, dos_energies,
                                        color=colors[idx], label=label)

        # get index of lowest and highest energy being plotted, used to help auto-scale DOS x-axis
        emin_idx = next(x[0] for x in enumerate(dos_energies) if x[1] >= emin)
        emax_idx = len(dos_energies) - next(x[0] for x in
                                            enumerate(reversed(dos_energies))
                                            if x[1] <= emax)

        # determine DOS x-axis range
        dos_xmin = 0 if Spin.down not in dos.densities else -max(
            dos.densities[Spin.down][emin_idx:emax_idx+1] * 1.05)
        dos_xmax = max([max(dos.densities[Spin.up][emin_idx:emax_idx]) *
                        1.05, abs(dos_xmin)])

        # set up the DOS x-axis and add Fermi level line
        dos_ax.set_xlim(dos_xmin, dos_xmax)
        dos_ax.set_xticklabels([])
        dos_ax.hlines(y=0, xmin=dos_xmin, xmax=dos_xmax, color="k", lw=2)
        dos_ax.set_xlabel('DOS', fontsize=self.axis_fontsize, family=self.font)

        # add legend for band structure
        if self.bs_legend:
            handles = []

            if bs_projection is None:
                handles = [mlines.Line2D([], [], linewidth=2,
                                         color='k', label='spin up'),
                           mlines.Line2D([], [], linewidth=2,
                                         color='b', linestyle="dotted",
                                         label='spin down')]

            elif bs_projection.lower() == "elements":
                colors = ['b', 'r', 'g']
                for idx, el in enumerate(elements):
                    handles.append(mlines.Line2D([], [],
                                                 linewidth=2,
                                                 color=colors[idx], label=el))

            bs_ax.legend(handles=handles, fancybox=True,
                         prop={'size': self.legend_fontsize,
                               'family': self.font}, loc=self.bs_legend)

        # add legend for DOS
        if self.dos_legend:
            dos_ax.legend(fancybox=True, prop={'size': self.legend_fontsize,
                                               'family': self.font},
                          loc=self.dos_legend)

        mplt.subplots_adjust(wspace=0.1)
        return mplt

    @staticmethod
    def _rgbline(ax, k, e, red, green, blue, alpha=1, linestyles="solid"):
        """
        An RGB colored line for plotting.
        creation of segments based on:
        http://nbviewer.ipython.org/urls/raw.github.com/dpsanders/matplotlib-examples/master/colorline.ipynb
        Args:
            ax: matplotlib axis
            k: x-axis data (k-points)
            e: y-axis data (energies)
            red: red data
            green: green data
            blue: blue data
            alpha: alpha values data
            linestyles: linestyle for plot (e.g., "solid" or "dotted")
        """
        from matplotlib.collections import LineCollection

        pts = np.array([k, e]).T.reshape(-1, 1, 2)
        seg = np.concatenate([pts[:-1], pts[1:]], axis=1)

        nseg = len(k) - 1
        r = [0.5 * (red[i] + red[i + 1]) for i in range(nseg)]
        g = [0.5 * (green[i] + green[i + 1]) for i in range(nseg)]
        b = [0.5 * (blue[i] + blue[i + 1]) for i in range(nseg)]
        a = np.ones(nseg, np.float) * alpha
        lc = LineCollection(seg, colors=list(zip(r, g, b, a)),
                            linewidth=2, linestyles=linestyles)
        ax.add_collection(lc)

    @staticmethod
    def _get_colordata(bs, elements, bs_projection):
        """
        Get color data, including projected band structures
        Args:
            bs: Bandstructure object
            elements: elements (in desired order) for setting to blue, red, green
            bs_projection: None for no projection, "elements" for element projection

        Returns:

        """
        contribs = {}
        if bs_projection and bs_projection.lower() == "elements":
            projections = bs.get_projection_on_elements()

        for spin in (Spin.up, Spin.down):
            if spin in bs.bands:
                contribs[spin] = []
                for band_idx in range(bs.nb_bands):
                    colors = []
                    for k_idx in range(len(bs.kpoints)):
                        if bs_projection and bs_projection.lower() == "elements":
                            c = [0, 0, 0]
                            projs = projections[spin][band_idx][k_idx]
                            total = sum(projs.values())
                            if total > 0:
                                for idx, e in enumerate(elements):
                                    c[idx] = projs[e]/total  # min is to handle round errors

                            c = [c[1], c[2], c[0]]  # prefer blue, then red, then green

                        else:
                            c = [0, 0, 0] if spin == Spin.up \
                                else [0, 0, 1]  # black for spin up, blue for spin down

                        colors.append(c)

                    contribs[spin].append(colors)
                contribs[spin] = np.array(contribs[spin])

        return contribs

class BoltztrapPlotter(object):
    """
    class containing methods to plot the data from Boltztrap.

    Args:
        bz: a BoltztrapAnalyzer object
    """

    def __init__(self, bz):
        self._bz = bz

    def _plot_doping(self, temp):
        import matplotlib.pyplot as plt
        if len(self._bz.doping) != 0:
            limit = 2.21e15
            plt.axvline(self._bz.mu_doping['n'][temp][0], linewidth=3.0,
                        linestyle="--")
            plt.text(self._bz.mu_doping['n'][temp][0] + 0.01,
                     limit,
                     "$n$=10$^{" + str(
                         math.log10(self._bz.doping['n'][0])) + "}$",
                     color='b')
            plt.axvline(self._bz.mu_doping['n'][temp][-1], linewidth=3.0,
                        linestyle="--")
            plt.text(self._bz.mu_doping['n'][temp][-1] + 0.01,
                     limit,
                     "$n$=10$^{" + str(math.log10(self._bz.doping['n'][-1]))
                     + "}$", color='b')
            plt.axvline(self._bz.mu_doping['p'][temp][0], linewidth=3.0,
                        linestyle="--")
            plt.text(self._bz.mu_doping['p'][temp][0] + 0.01,
                     limit,
                     "$p$=10$^{" + str(
                         math.log10(self._bz.doping['p'][0])) + "}$",
                     color='b')
            plt.axvline(self._bz.mu_doping['p'][temp][-1], linewidth=3.0,
                        linestyle="--")
            plt.text(self._bz.mu_doping['p'][temp][-1] + 0.01,
                     limit, "$p$=10$^{" +
                     str(math.log10(self._bz.doping['p'][-1])) + "}$",
                     color='b')

    def _plot_bg_limits(self):
        import matplotlib.pyplot as plt
        plt.axvline(0.0, color='k', linewidth=3.0)
        plt.axvline(self._bz.gap, color='k', linewidth=3.0)

    def plot_seebeck_mu(self, temp=600, output='eig', xlim=None):
        """
        Plot the seebeck coefficient in function of Fermi level

        Args:
            temp:
                the temperature
            xlim:
                a list of min and max fermi energy by default (0, and band gap)
        Returns:
            a matplotlib object
        """
        import matplotlib.pyplot as plt
        seebeck = self._bz.get_seebeck(output=output, doping_levels=False)[
            temp]
        plt.plot(self._bz.mu_steps, seebeck,
                 linewidth=3.0)
        self._plot_bg_limits()
        self._plot_doping(temp)
        if output == 'eig':
            plt.legend(['S$_1$', 'S$_2$', 'S$_3$'])
        if xlim is None:
            plt.xlim(-0.5, self._bz.gap + 0.5)
        else:
            plt.xlim(xlim[0], xlim[1])
        plt.ylabel("Seebeck \n coefficient  ($\mu$V/K)", fontsize=30.0)
        plt.xlabel("E-E$_f$ (eV)", fontsize=30)
        plt.xticks(fontsize=25)
        plt.yticks(fontsize=25)
        return plt

    def plot_conductivity_mu(self, temp=600, output='eig',
                             relaxation_time=1e-14, xlim=None):
        """
        Plot the conductivity in function of Fermi level. Semi-log plot

        Args:
            temp: the temperature
            xlim: a list of min and max fermi energy by default (0, and band
                gap)
            tau: A relaxation time in s. By default none and the plot is by
               units of relaxation time

        Returns:
            a matplotlib object
        """
        import matplotlib.pyplot as plt
        cond = self._bz.get_conductivity(relaxation_time=relaxation_time,
                                         output=output, doping_levels=False)[
            temp]
        plt.semilogy(self._bz.mu_steps, cond, linewidth=3.0)
        self._plot_bg_limits()
        self._plot_doping(temp)
        if output == 'eig':
            plt.legend(['$\sigma_1$', '$\sigma_2$', '$\sigma_3$'])
        if xlim is None:
            plt.xlim(-0.5, self._bz.gap + 0.5)
        else:
            plt.xlim(xlim)
        plt.ylim([1e13 * relaxation_time, 1e20 * relaxation_time])
        plt.ylabel("conductivity,\n $\sigma$ (1/($\Omega$ m))", fontsize=30.0)
        plt.xlabel("E-E$_f$ (eV)", fontsize=30.0)
        plt.xticks(fontsize=25)
        plt.yticks(fontsize=25)
        return plt

    def plot_power_factor_mu(self, temp=600, output='eig',
                             relaxation_time=1e-14, xlim=None):
        """
        Plot the power factor in function of Fermi level. Semi-log plot

        Args:
            temp: the temperature
            xlim: a list of min and max fermi energy by default (0, and band
                gap)
            tau: A relaxation time in s. By default none and the plot is by
               units of relaxation time

        Returns:
            a matplotlib object
        """
        import matplotlib.pyplot as plt
        pf = self._bz.get_power_factor(relaxation_time=relaxation_time,
                                       output=output, doping_levels=False)[
            temp]
        plt.semilogy(self._bz.mu_steps, pf, linewidth=3.0)
        self._plot_bg_limits()
        self._plot_doping(temp)
        if output == 'eig':
            plt.legend(['PF$_1$', 'PF$_2$', 'PF$_3$'])
        if xlim is None:
            plt.xlim(-0.5, self._bz.gap + 0.5)
        else:
            plt.xlim(xlim)
        plt.ylabel("Power factor, ($\mu$W/(mK$^2$))", fontsize=30.0)
        plt.xlabel("E-E$_f$ (eV)", fontsize=30.0)
        plt.xticks(fontsize=25)
        plt.yticks(fontsize=25)
        return plt

    def plot_zt_mu(self, temp=600, output='eig', relaxation_time=1e-14,
                   xlim=None):
        """
        Plot the ZT in function of Fermi level.

        Args:
            temp: the temperature
            xlim: a list of min and max fermi energy by default (0, and band
                gap)
            tau: A relaxation time in s. By default none and the plot is by
               units of relaxation time

        Returns:
            a matplotlib object
        """
        import matplotlib.pyplot as plt
        zt = self._bz.get_zt(relaxation_time=relaxation_time, output=output,
                             doping_levels=False)[temp]
        plt.plot(self._bz.mu_steps, zt, linewidth=3.0)
        self._plot_bg_limits()
        self._plot_doping(temp)
        if output == 'eig':
            plt.legend(['ZT$_1$', 'ZT$_2$', 'ZT$_3$'])
        if xlim is None:
            plt.xlim(-0.5, self._bz.gap + 0.5)
        else:
            plt.xlim(xlim)
        plt.ylabel("ZT", fontsize=30.0)
        plt.xlabel("E-E$_f$ (eV)", fontsize=30.0)
        plt.xticks(fontsize=25)
        plt.yticks(fontsize=25)
        return plt

    def plot_dos(self, sigma=0.05):
        """
        plot dos

        Args:
            sigma: a smearing

        Returns:
            a matplotlib object
        """
        plotter = DosPlotter(sigma=sigma)
        plotter.add_dos("t", self._bz.dos)
        return plotter.get_plot()

    def plot_carriers(self, temp=300):
        """
        Plot the carrier concentration in function of Fermi level

        Args:
            temp: the temperature

        Returns:
            a matplotlib object
        """
        import matplotlib.pyplot as plt
        plt.semilogy(self._bz.mu_steps,
                     abs(self._bz.carrier_conc[temp] / (self._bz.vol * 1e-24)),
                     linewidth=3.0, color='r')
        self._plot_bg_limits()
        self._plot_doping(temp)
        plt.xlim(-0.5, self._bz.gap + 0.5)
        plt.ylim(1e14, 1e22)
        plt.ylabel("carrier concentration (cm-3)", fontsize=30.0)
        plt.xlabel("E-E$_f$ (eV)", fontsize=30)
        plt.xticks(fontsize=25)
        plt.yticks(fontsize=25)
        return plt

    def plot_hall_carriers(self, temp=300):
        """
        Plot the Hall carrier concentration in function of Fermi level

        Args:
            temp: the temperature

        Returns:
            a matplotlib object
        """
        import matplotlib.pyplot as plt
        hall_carriers = [abs(i) for i in
                         self._bz.get_hall_carrier_concentration()[temp]]
        plt.semilogy(self._bz.mu_steps,
                     hall_carriers,
                     linewidth=3.0, color='r')
        self._plot_bg_limits()
        self._plot_doping(temp)
        plt.xlim(-0.5, self._bz.gap + 0.5)
        plt.ylim(1e14, 1e22)
        plt.ylabel("Hall carrier concentration (cm-3)", fontsize=30.0)
        plt.xlabel("E-E$_f$ (eV)", fontsize=30)
        plt.xticks(fontsize=25)
        plt.yticks(fontsize=25)
        return plt

    def plot_fermi_surface(self, structure=None, isolevel=None):
        """
        Plot the Fermi surface at a aspecific energy value

        Args:
            bz_lattice: structure object of the material
            isolevel: energy value fo fermi surface, Default: max energy value + 0.1eV

        Returns:
            a matplotlib object

        Note: Experimental
        """
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        from pymatgen.electronic_structure.plotter import plot_brillouin_zone
        try:
            from skimage import measure
        except ImportError:
            raise BoltztrapError(
                "skimage package should be installed to use this function")

        fig = None

        data = self._bz.fermi_surface_data

        if not isolevel:
            isolevel = max(data[0].flat) - Energy(0.1, "eV").to("Ry")

        verts, faces = measure.marching_cubes(data[0], isolevel)
        verts -= 1
        verts2 = np.dot(verts,
                        data[1].cell / np.array(data[0].shape)[:, np.newaxis])
        verts2 /= max(verts2.flat) / 1.5

        cx, cy, cz = [
            (max(verts2[:, i]) - min(verts2[:, i])) / 2 + min(verts2[:, i]) for
            i in range(3)]

        if structure is not None:
            kpath = HighSymmKpath(structure).kpath
            lines = [[kpath['kpoints'][k] for k in p] for p in kpath['path']]
            fig = plot_brillouin_zone(bz_lattice=structure.reciprocal_lattice,
                                      lines=lines, labels=kpath['kpoints'])

        if fig:
            ax = fig.gca()
            ax.plot_trisurf(verts2[:, 0] - cx, verts2[:, 1] - cy, faces,
                            verts2[:, 2] - cz, lw=0)
        else:
            fig = plt.figure()
            ax = fig.add_subplot(111, projection='3d')
            ax.plot_trisurf(verts2[:, 0] - cx, verts2[:, 1] - cy, faces,
                            verts2[:, 2] - cz, lw=0)
            ax.set_xlim3d(-1, 1)
            ax.set_ylim3d(-1, 1)
            ax.set_zlim3d(-1, 1)
            ax.set_aspect('equal')
            ax.axis("off")

        return fig, ax


def plot_wigner_seitz(lattice, ax=None, **kwargs):
    """
    Adds the skeleton of the Wigner-Seitz cell of the lattice to a matplotlib Axes

    Args:
        lattice: Lattice object
        ax: matplotlib :class:`Axes` or None if a new figure should be created.
        kwargs: kwargs passed to the matplotlib function 'plot'. Color defaults to black
            and linewidth to 1.

    Returns:
        matplotlib figure and matplotlib ax
    """
    ax, fig, plt = get_ax3d_fig_plt(ax)

    if "color" not in kwargs:
        kwargs["color"] = "k"
    if "linewidth" not in kwargs:
        kwargs["linewidth"] = 1

    bz = lattice.get_wigner_seitz_cell()
    ax, fig, plt = get_ax3d_fig_plt(ax)
    for iface in range(len(bz)):
        for line in itertools.combinations(bz[iface], 2):
            for jface in range(len(bz)):
                if iface < jface and any(np.all(line[0] == x) for x in bz[jface])\
                        and any(np.all(line[1] == x) for x in bz[jface]):
                    ax.plot(*zip(line[0], line[1]), **kwargs)

    return fig, ax


def plot_lattice_vectors(lattice, ax=None, **kwargs):
    """
    Adds the basis vectors of the lattice provided to a matplotlib Axes

    Args:
        lattice: Lattice object
        ax: matplotlib :class:`Axes` or None if a new figure should be created.
        kwargs: kwargs passed to the matplotlib function 'plot'. Color defaults to green
            and linewidth to 3.

    Returns:
        matplotlib figure and matplotlib ax
    """
    ax, fig, plt = get_ax3d_fig_plt(ax)

    if "color" not in kwargs:
        kwargs["color"] = "g"
    if "linewidth" not in kwargs:
        kwargs["linewidth"] = 3

    vertex1 = lattice.get_cartesian_coords([0.0, 0.0, 0.0])
    vertex2 = lattice.get_cartesian_coords([1.0, 0.0, 0.0])
    ax.plot(*zip(vertex1, vertex2), **kwargs)
    vertex2 = lattice.get_cartesian_coords([0.0, 1.0, 0.0])
    ax.plot(*zip(vertex1, vertex2), **kwargs)
    vertex2 = lattice.get_cartesian_coords([0.0, 0.0, 1.0])
    ax.plot(*zip(vertex1, vertex2), **kwargs)

    return fig, ax


def plot_path(line, lattice=None, coords_are_cartesian=False, ax=None, **kwargs):
    """
    Adds a line passing through the coordinates listed in 'line' to a matplotlib Axes

    Args:
        line: list of coordinates.
        lattice: Lattice object used to convert from reciprocal to cartesian coordinates
        coords_are_cartesian: Set to True if you are providing
            coordinates in cartesian coordinates. Defaults to False.
            Requires lattice if False.
        ax: matplotlib :class:`Axes` or None if a new figure should be created.
        kwargs: kwargs passed to the matplotlib function 'plot'. Color defaults to red
            and linewidth to 3.

    Returns:
        matplotlib figure and matplotlib ax
    """

    ax, fig, plt = get_ax3d_fig_plt(ax)

    if "color" not in kwargs:
        kwargs["color"] = "r"
    if "linewidth" not in kwargs:
        kwargs["linewidth"] = 3

    for k in range(1, len(line)):
        vertex1 = line[k-1]
        vertex2 = line[k]
        if not coords_are_cartesian:
            if lattice is None:
                raise ValueError("coords_are_cartesian False requires the lattice")
            vertex1 = lattice.get_cartesian_coords(vertex1)
            vertex2 = lattice.get_cartesian_coords(vertex2)
        ax.plot(*zip(vertex1, vertex2), **kwargs)

    return fig, ax


def plot_labels(labels, lattice=None, coords_are_cartesian=False, ax=None, **kwargs):
    """
    Adds labels to a matplotlib Axes

    Args:
        labels: dict containing the label as a key and the coordinates as value.
        lattice: Lattice object used to convert from reciprocal to cartesian coordinates
        coords_are_cartesian: Set to True if you are providing.
            coordinates in cartesian coordinates. Defaults to False.
            Requires lattice if False.
        ax: matplotlib :class:`Axes` or None if a new figure should be created.
        kwargs: kwargs passed to the matplotlib function 'text'. Color defaults to blue
            and size to 25.

    Returns:
        matplotlib figure and matplotlib ax
    """
    ax, fig, plt = get_ax3d_fig_plt(ax)

    if "color" not in kwargs:
        kwargs["color"] = "b"
    if "size" not in kwargs:
        kwargs["size"] = 25

    for k, coords in labels.items():
        label = k
        if k.startswith("\\") or k.find("_") != -1:
            label = "$" + k + "$"
        off = 0.01
        if coords_are_cartesian:
            coords = np.array(coords)
        else:
            if lattice is None:
                raise ValueError("coords_are_cartesian False requires the lattice")
            coords = lattice.get_cartesian_coords(coords)
        ax.text(*(coords + off), s=label, **kwargs)

    return fig, ax


def fold_point(p, lattice, coords_are_cartesian=False):
    """
    Folds a point with coordinates p inside the first Brillouin zone of the lattice.

    Args:
        p: coordinates of one point
        lattice: Lattice object used to convert from reciprocal to cartesian coordinates
        coords_are_cartesian: Set to True if you are providing
            coordinates in cartesian coordinates. Defaults to False.

    Returns:
        The cartesian coordinates folded inside the first Brillouin zone
    """

    if coords_are_cartesian:
        p = lattice.get_fractional_coords(p)
    else:
        p = np.array(p)

    p = np.mod(p+0.5-1e-10, 1)-0.5+1e-10
    p = lattice.get_cartesian_coords(p)

    closest_lattice_point = None
    smallest_distance = 10000
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for k in (-1, 0, 1):
                lattice_point = np.dot((i, j, k), lattice.matrix)
                dist = np.linalg.norm(p - lattice_point)
                if closest_lattice_point is None or dist < smallest_distance:
                    closest_lattice_point = lattice_point
                    smallest_distance = dist

    if not np.allclose(closest_lattice_point, (0, 0, 0)):
        p = p - closest_lattice_point

    return p


def plot_points(points, lattice=None, coords_are_cartesian=False, fold=False, ax=None, **kwargs):
    """
    Adds Points to a matplotlib Axes

    Args:
        points: list of coordinates
        lattice: Lattice object used to convert from reciprocal to cartesian coordinates
        coords_are_cartesian: Set to True if you are providing
            coordinates in cartesian coordinates. Defaults to False.
            Requires lattice if False.
        fold: whether the points should be folded inside the first Brillouin Zone.
            Defaults to False. Requires lattice if True.
        ax: matplotlib :class:`Axes` or None if a new figure should be created.
        kwargs: kwargs passed to the matplotlib function 'scatter'. Color defaults to blue

    Returns:
        matplotlib figure and matplotlib ax
    """
    ax, fig, plt = get_ax3d_fig_plt(ax)

    if "color" not in kwargs:
        kwargs["color"] = "b"

    if (not coords_are_cartesian or fold) and lattice is None:
        raise ValueError("coords_are_cartesian False or fold True require the lattice")

    for p in points:

        if fold:
            p = fold_point(p, lattice, coords_are_cartesian=coords_are_cartesian)

        elif not coords_are_cartesian:
            p = lattice.get_cartesian_coords(p)

        ax.scatter(*p, **kwargs)

    return fig, ax


@add_fig_kwargs
def plot_brillouin_zone_from_kpath(kpath, **kwargs):

    """
    Gives the plot (as a matplotlib object) of the symmetry line path in
        the Brillouin Zone.

    Args:
        kpath (HighSymmKpath): a HighSymmKPath object
        **kwargs: provided by add_fig_kwargs decorator

    Returns:
        a matplotlib figure and matplotlib_ax

    """
    lines = [[kpath.kpath['kpoints'][k] for k in p]
             for p in kpath.kpath['path']]
    return plot_brillouin_zone(bz_lattice=kpath.prim_rec, lines=lines,
                               labels=kpath.kpath['kpoints'], **kwargs)


@add_fig_kwargs
def plot_brillouin_zone(bz_lattice, lines=None, labels=None, kpoints=None,
                        fold=False, coords_are_cartesian=False,
                        ax=None, **kwargs):
    """
    Plots a 3D representation of the Brillouin zone of the structure.
    Can add to the plot paths, labels and kpoints

    Args:
        bz_lattice: Lattice object of the Brillouin zone
        lines: list of lists of coordinates. Each list represent a different path
        labels: dict containing the label as a key and the coordinates as value.
        kpoints: list of coordinates
        fold: whether the points should be folded inside the first Brillouin Zone.
            Defaults to False. Requires lattice if True.
        coords_are_cartesian: Set to True if you are providing
            coordinates in cartesian coordinates. Defaults to False.
        ax: matplotlib :class:`Axes` or None if a new figure should be created.
        kwargs: provided by add_fig_kwargs decorator

    Returns:
        matplotlib figure and matplotlib ax
    """

    fig, ax = plot_lattice_vectors(bz_lattice, ax=ax)
    plot_wigner_seitz(bz_lattice, ax=ax)
    if lines is not None:
        for line in lines:
            plot_path(line, bz_lattice,
                      coords_are_cartesian=coords_are_cartesian, ax=ax)

    if labels is not None:
        plot_labels(labels, bz_lattice,
                    coords_are_cartesian=coords_are_cartesian, ax=ax)
        plot_points(labels.values(), bz_lattice,
                    coords_are_cartesian=coords_are_cartesian,
                    fold=False, ax=ax)

    if kpoints is not None:
        plot_points(kpoints, bz_lattice,
                    coords_are_cartesian=coords_are_cartesian,
                    ax=ax, fold=fold)

    ax.set_xlim3d(-1, 1)
    ax.set_ylim3d(-1, 1)
    ax.set_zlim3d(-1, 1)

    ax.set_aspect('equal')
    ax.axis("off")

    return fig


def plot_ellipsoid(hessian, center, lattice=None, rescale=1.0, ax=None, coords_are_cartesian=False, **kwargs):
    """
    Plots a 3D ellipsoid rappresenting the Hessian matrix in input.
    Useful to get a graphical visualization of the effective mass
    of a band in a single k-point.
    
    Args:
        hessian: the Hessian matrix
        center: the center of the ellipsoid in reciprocal coords (Default)
        lattice: Lattice object of the Brillouin zone
        rescale: factor for size scaling of the ellipsoid
        ax: matplotlib :class:`Axes` or None if a new figure should be created.
        coords_are_cartesian: Set to True if you are providing a center in
            cartesian coordinates. Defaults to False.
        kwargs: kwargs passed to the matplotlib function 'plot_wireframe'. Color defaults to blue, rstride and cstride
            default to 4, alpha defaults to 0.2.
    Returns:
        matplotlib figure and matplotlib ax
    Example of use:
        fig,ax=plot_wigner_seitz(struct.reciprocal_lattice)
        plot_ellipsoid(hessian,[0.0,0.0,0.0], struct.reciprocal_lattice,ax=ax)
    """
    
    if (not coords_are_cartesian) and lattice is None:
        raise ValueError("coords_are_cartesian False or fold True require the lattice")
    
    if not coords_are_cartesian:
        center = lattice.get_cartesian_coords(center)

    if "color" not in kwargs:
        kwargs["color"] = "b"
    if "rstride" not in kwargs:
        kwargs["rstride"] = 4
    if "cstride" not in kwargs:
        kwargs["cstride"] = 4
    if "alpha" not in kwargs:
        kwargs["alpha"] = 0.2

    # calculate the ellipsoid
    # find the rotation matrix and radii of the axes
    U, s, rotation = np.linalg.svd(hessian)
    radii = 1.0/np.sqrt(s)
    
    # from polar coordinates
    u = np.linspace(0.0, 2.0 * np.pi, 100)
    v = np.linspace(0.0, np.pi, 100)
    x = radii[0] * np.outer(np.cos(u), np.sin(v)) 
    y = radii[1] * np.outer(np.sin(u), np.sin(v))
    z = radii[2] * np.outer(np.ones_like(u), np.cos(v))
    for i in range(len(x)):
        for j in range(len(x)):
            [x[i, j], y[i, j], z[i, j]] = np.dot([x[i, j], y[i, j], z[i, j]], rotation)*rescale + center

    # add the ellipsoid to the current axes
    ax, fig, plt = get_ax3d_fig_plt(ax)
    ax.plot_wireframe(x, y, z,  **kwargs)

    return fig, ax
