#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright 2017 D. de Vries

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

This file contains the definition the base `XMLComponent` and `DisciplineComponent` classes.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import abc
import os
import numpy as np

from abc import abstractmethod
from datetime import datetime
from lxml import etree
from typing import Optional, List, Union, Iterable
from openmdao.api import Group, IndepVarComp, ExplicitComponent
from openmdao.vectors.vector import Vector

from openlego.discipline import AbstractDiscipline
from openlego.xml import xml_safe_create_element, xml_to_dict, xpath_to_param, param_to_xpath, xml_merge

dir_path = os.path.dirname(os.path.realpath(__file__))


class XMLComponent(ExplicitComponent):
    """Abstract base class exposing an interface to use XML files for its in- and output.

    This subclass of `PromotingComponent` can automatically create ``OpenMDAO`` inputs and outputs based on given in-
    and output XML template files. For maximum flexibility it is possible to only specify inputs from an XML file and
    retain direct control over the definition of the outputs, or vice versa. It is also perfectly valid to add inputs
    even when an XML file is used to generate a set of inputs, or outputs when an XML file it used to generate outputs.
    It is even possible to generate in- and/or output parameters based on more than one XML file.

    This class exposes the functions `set_inputs_from_xml()` and `set_outputs_from_xml()` for this purpose. Lists of all
    parameters obtained from XML files are stored by this class for later inspection.

    The `solve_nonlinear()` method of the `Component` class is implemented to wrap the XML related operations such as
    reading in- and output data from the corresponding XML files during execution and storing it in this `Component`'s
    parameter dictionaries.

    A new abstract method is defined by this class, `execute()`, which assumes the role of the `solve_nonlinear()`
    function, in essence. A specific case of this class should implement this method to perform the actual calculations
    of an analysis tool using XML in- and/or output.

    Attributes
    ----------
        inputs_from_xml, outputs_from_xml : dict
            List of inputs, resp. outputs, taken from XML.

        data_folder : str('')
            Path to a folder in which to store data generated during the execution of this `XMLComponent`.

        keep_files : bool(False)
            Set to `True` to keep all temporary XML files generated by the `XMLComponent` during execution.

            This attribute is `False` by default, in which case all temporary in- and output XML files will be deleted
            after they are no longer needed by this component.

        base_file : str, optional
            Path to an XML file to keep up-to-date with the latest data from executions.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self,
                 input_xml=None,    # type: Optional[Union[str, etree._ElementTree]]
                 output_xml=None,   # type: Optional[Union[str, etree._ElementTree]]
                 data_folder='',    # type: str
                 keep_files=False,  # type: bool
                 base_file=None     # type: Optional[str]
                 ):
        # type: (...) -> None
        """Initialize the `XMLComponent`.

        Parameters
        ----------
            input_xml, output_xml : str or :obj:`etree._ElementTree`, optional
                Paths to or an `etree._ElementTree` of input, resp. output, XML files.

            data_folder : str
                Path to the folder in which to store temporary data files generated by this `XMLComponent`.

            keep_files : bool(False)
                Set to `True` to keep the temporary XML files after they are no longer needed.

            base_file : str, optional
                Path to a base XML file to keep up-to-date with all latest data from this `XMLComponent`.
        """
        super(XMLComponent, self).__init__()

        self.inputs_from_xml = dict()
        self.outputs_from_xml = dict()

        if input_xml is not None:
            self.set_inputs_from_xml(input_xml)

        if output_xml is not None:
            self.set_outputs_from_xml(output_xml)

        self.data_folder = data_folder
        self.keep_files = keep_files
        self.base_file = base_file

    def set_inputs_from_xml(self, input_xml):
        # type: (Union[str, etree._ElementTree]) -> None
        """Set inputs to the `Component` based on an input XML template file.

        Parameter names correspond to their XML elements' full XPaths, converted to valid ``OpenMDAO`` names using the
        `xpath_to_param()` method.

        Parameters
        ----------
            input_xml : str or :obj:`etree._ElementTree`
                Path to or an `etree._ElementTree` of an input XML file.
        """
        self.inputs_from_xml.clear()
        for xpath, value in xml_to_dict(input_xml).items():
            name = xpath_to_param(xpath)
            self.inputs_from_xml.update({name: value})

    def set_outputs_from_xml(self, output_xml):
        # type: (Union[str, etree._ElementTree]) -> None
        """Set outputs to the `Component` based on an output XML template file.

        Parameter names correspond to their XML elements' full XPaths, converted to valid ``OpenMDAO`` names using the
        `xpath_to_param()` method.

        Parameters
        ----------
            output_xml : str or :obj:`etree._ElementTree`
                Path to or an `etree._ElementTree` of an output XML file.
        """
        self.outputs_from_xml.clear()
        for xpath, value in xml_to_dict(output_xml).items():
            name = xpath_to_param(xpath)
            self.outputs_from_xml.update({name: value})

    @property
    def variables_from_xml(self):
        # type: () -> dict
        """:obj:`dict`: Dictionary of all XML inputs and outputs."""
        variables = self.inputs_from_xml.copy()
        variables.update(self.outputs_from_xml.copy())
        return variables

    def setup(self):
        for name, value in self.inputs_from_xml.items():
            self.add_input(name, value)

        for name, value in self.outputs_from_xml.items():
            self.add_output(name, value)

    @abstractmethod
    def execute(self, input_xml=None, output_xml=None):
        # type: (Optional[str], Optional[str]) -> None
        """Execute the tool using the given input XML file. Write the results to the given output XML file.

        Parameters
        ----------
            input_xml, output_xml : str, optional
                Path to the input, resp. output, XML file.
        """
        raise NotImplementedError

    def compute(self, inputs, outputs):
        # type: (Vector, Vector) -> None
        """Write the input XML file, call `execute()`, and read the output XML file to obtain the results.

        Parameters
        ----------
            inputs : `Vector`
                Input parameters.

            outputs : `Vector`
                Output parameters.
        """

        # Create file names
        salt = datetime.now().strftime('%Y%m%d%H%M%f')
        input_xml = os.path.join(self.data_folder, self.name + '_in_%s.xml' % salt)
        output_xml = os.path.join(self.data_folder, self.name + '_out_%s.xml' % salt)

        if self.inputs_from_xml:
            # Create new root element and an ElementTree
            root = etree.Element(param_to_xpath(self.inputs_from_xml.keys()[0]).split('/')[1])
            doc = etree.ElementTree(root)

            # Convert all XML param names to XPaths and add new elements to the tree correspondingly
            for param in self.inputs_from_xml:
                xml_safe_create_element(doc, param_to_xpath(param), inputs[param])

            # Write the tree to an XML file
            doc.write(input_xml, pretty_print=True, xml_declaration=True, encoding='utf-8')
            if self.base_file is not None:
                xml_merge(self.base_file, input_xml)

        # Call execute
        if self.base_file is not None:
            self.execute(self.base_file, output_xml)
            xml_merge(self.base_file, output_xml)
        else:
            self.execute(input_xml, output_xml)

        # If files should not be kept, delete the input XML file
        if not self.keep_files:
            try:
                os.remove(input_xml)
            except OSError:
                pass

        if self.outputs_from_xml:
            # Extract the results from the output xml
            for xpath, value in xml_to_dict(output_xml).items():
                name = xpath_to_param(xpath)
                if name in self.outputs_from_xml:
                    outputs[name] = value

            # If files should not be kept, delete the output XML file
            if not self.keep_files:
                try:
                    os.remove(output_xml)
                except OSError:
                    pass

    def xml_params_as_indep_vars(self, group, params, values, aliases=None):
        # type: (Group, List[str], Union[np.ndarray, Iterable], Optional[List[str]]) -> None
        """Create `IndepVarComp`s for given input params of this `XMLComponent`.

        Parameters
        ----------
            group : :obj:`Group`
                `Group` to add the `IndepVarComp`s to.

            params : list of str
                List of param names. These need to exist in this `XMLComponent`.

            values : :obj:`np.ndarray` or list of numbers
                List of (initial) values for all `IndepVarComp`s.

            aliases : list of str, optional
                List of aliases (promoted names) to give the `IndepVarComp`s.
        """
        if len(params) != len(values) or (aliases is None and len(params) != len(aliases)):
            raise ValueError('number of params, values and optionally aliases needs to be the same')

        for param in params:
            if param not in self.inputs_from_xml:
                raise ValueError('at least one param given is not a param of this XMLComponent (%s)' % param)

        for index, param in enumerate(params):
            if aliases is None:
                alias = 'INDEP_' + param_to_xpath(param).split('/')[-1].split('[')[0]
            else:
                alias = aliases[index]

            group.add(alias, IndepVarComp(alias, val=values[index]), promotes=[alias])
            group.connect(alias, param)


class DisciplineComponent(XMLComponent):
    """Specialized `XMLComponent` wrapping an `AbstractDiscipline`.

    This version of `XMLComponent` defines in- and output variables based on the in- and output template XML files
    generated by a subclass of `AbstractDiscipline`. The `execute()` method simply forwards to that of the discipline.

    Attributes
    ----------
        discipline
    """

    def __init__(self, discipline, data_folder='', keep_files=False, base_file=None):
        # type: (AbstractDiscipline, Optional[str]) -> None
        """Initialize a `Component` using a given `discipline`.

        Stores a reference to the given `discipline`. The in- and output XML templates should already exist at the paths
        specified in the `discipline`. This constructor uses those files to create the ``OpenMDAO`` `params` and
        `unknowns` using the methods exposed by the `XMLComponent` class this class inherits from.

        Parameters
        ----------
            discipline : :obj:`AbstractDiscipline`
                Instance of a subclass of `AbstractDiscipline` this `Component` will represent.

            data_folder : str(''), optional
                Path to a folder in which to store (temporary) data of this `Component` during execution.

            keep_files : bool(False), optional
                Set to `True` to keep the data files generated by this `Component` during execution.

            base_file : str, optional
                Path to an XML file which should be kept up-to-date with the latest data, if required.

        Notes
        -----
            Although this constructor could use the supplied `discipline` to also automatically generate its in- and
            output XML templates on the fly, the user is left in control of their generation. This is to allow for a
            `discipline` to generate different in- and output templates dynamically based on certain parameters. During
            execution only the static methods of the `discipline`s are used. Hence, any instance variables will not be
            accessible then. Therefore it is impossible to guarantee consistency if the in- and output XML files are
            generated here.
        """
        self._discipline = discipline
        super(DisciplineComponent, self).__init__(self._discipline.in_file, self._discipline.out_file,
                                                  data_folder, keep_files, base_file)

    @property
    def discipline(self):
        # type: () -> AbstractDiscipline
        """:obj:`AbstractDiscipline`: Read-only reference to the specific discipline this `Component` wraps."""
        return self._discipline

    def setup(self):
        # type: () -> None
        """Approximate all gradients using finite difference."""
        super(DisciplineComponent, self).setup()
        self.approx_partials('*', '*')

    def execute(self, input_xml=None, output_xml=None):
        # type: (str, str) -> None
        """Call the `execute()` method of this `Component`'s discipline.

        Parameters
        ----------
            input_xml : str
                Path to the input XML file.

            output_xml : str
                Path to the output XML file.

        Raises
        ------
            ValueError
                If either no `input_xml` or `output_xml` path was specified.

        Notes
        -----
            Since this class inherits from `XMLComponent` the interface, including the optionality of its arguments, are
            left untouched. For this method this means the `input_xml` and `output_xml` parameters are strictly
            optional. However, in the context of the `DisciplineComponent` they should always be given. Therefore an
            exception is raised here when one of them or both are omitted.
        """
        if input_xml is None or output_xml is None:
            raise ValueError('Both an input_xml and output_xml path are expected.')
        self.discipline.execute(input_xml, output_xml)