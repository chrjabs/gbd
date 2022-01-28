# GBD Benchmark Database (GBD)
# Copyright (C) 2020 Markus Iser, Luca Springer, Karlsruhe Institute of Technology (KIT)
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import sqlite3
import tatsu
import os
import numpy as np
import pandas as pd

from contextlib import ExitStack

from gbd_tool.query_builder import GBDQuery
from gbd_tool.db import Database
import gbd_tool.util as util
from gbd_tool.util import eprint


class GBDException(Exception):
    pass


class GBD:
    # Create a new GBD object which operates on the given databases
    def __init__(self, db_string, context='cnf', jobs=1, tlim=5000, mlim=2000, flim=1000, separator=" ", join_type="LEFT", verbose=False):
        self.databases = db_string.split(os.pathsep)
        self.context = context
        self.jobs = jobs
        self.tlim = tlim  # time limit (seconds)
        self.mlim = mlim  # memory limit (mega bytes)
        self.flim = flim  # file size limit (mega bytes)
        self.separator = separator
        self.join_type = join_type
        self.verbose = verbose
        self.database = Database(self.databases, self.verbose)

    def __enter__(self):
        with ExitStack() as stack:
            stack.enter_context(self.database)
            self._stack = stack.pop_all()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._stack.__exit__(exc_type, exc, traceback)

    def get_limits(self) -> dict():
        return { 'tlim': self.tlim, 'mlim': self.mlim, 'flim': self.flim }

    def get_databases(self):
        return list(self.database.get_databases())

    def get_database_path(self, dbname):
        return self.database.dpath(dbname)

    # Get all features
    def get_features(self, dbname=None):
        return self.database.get_features(tables=True, views=True, database=dbname)

    # Get all material features
    def get_material_features(self, dbname=None):
        return self.database.get_features(tables=True, views=False, database=dbname)

    # Get all virtual features
    def get_virtual_features(self, dbname=None):
        return self.database.get_features(tables=False, views=True, database=dbname)

    # Check for existence of given feature
    def feature_exists(self, name):
        return name in self.get_features()

    # Creates the given feature
    def create_feature(self, name, default_value=None):
        if not self.feature_exists(name):
            self.database.create_feature(name, default_value)
        else:
            raise GBDException("Feature '{}' does already exist".format(name))

    # Removes the given feature
    def delete_feature(self, name):
        if self.feature_exists(name):
            self.database.delete_feature(name)
        else:
            raise GBDException("Feature '{}' does not exist or is virtual".format(name))

    # Rename the given feature
    def rename_feature(self, old_name, new_name):
        if not self.feature_exists(old_name):
            raise GBDException("Feature '{}' does not exist or is virtual".format(old_name))
        elif self.feature_exists(new_name):
            raise GBDException("Feature '{}' does already exist".format(new_name))
        else:
            self.database.rename_feature(old_name, new_name)

    # Retrieve information about a specific feature
    def get_feature_info(self, name):
        return self.database.feature_info(name)

    # Set the attribute value for the given hashes
    def set_attribute(self, feature, value, query, hashes=[], force=False):
        if not feature in self.get_material_features():
            raise GBDException("Feature '{}' missing or virtual".format(feature))
        hash_list = hashes
        if query:
            hash_list = [hash[0] for hash in self.query_search(query, hashes)]
        try:
            self.database.set_values(feature, value, hash_list)
        except Exception as err:
            raise GBDException(str(err))

    # Remove the attribute value for the given hashes
    def remove_attributes(self, feature, hash_list):
        if not feature in self.get_material_features():
            raise GBDException("Feature '{}' not found".format(feature))
        self.database.delete_hashes(feature, hash_list)

    def query_search(self, gbd_query=None, hashes=[], resolve=[], collapse="GROUP_CONCAT", group_by="hash"):
        try:
            query_builder = GBDQuery(self.database, self.join_type, collapse)
            sql = query_builder.build_query(gbd_query, hashes, resolve or [], group_by or "hash")
            return self.database.query(sql)
        except sqlite3.OperationalError as err:
            raise GBDException("Database Operational Error: {}".format(str(err)))
        except tatsu.exceptions.FailedParse as err:
            raise GBDException("Parser Error: {}".format(str(err)))


    def query_search2(self, gbd_query=None, feature='', hashes=[], resolve=[], collapse="GROUP_CONCAT", group_by="hash", tmout=[], dict = "default"):

        #what values to replace
        if dict == "default":
            replace_dict = {
                "replace_tuples": [("timeout", np.inf), ("memout", np.inf), ("error", np.NaN)],
            }

        #no features selected error
        if resolve==[]:
            #print("No features selected.")
            raise GBDException("No features selected.")
        if feature == '':
            # MI: classification code does not belong here
            #print("No classification feature selected.")
            raise GBDException("No classification feature selected.")


        # two matrices, one for the normal, one for the timeout features
        result1 = self.query_search(gbd_query, hashes, resolve+[feature], collapse, group_by) #family
        result2 = self.query_search(gbd_query, hashes, tmout, collapse, group_by) #features

        #conversion to the dataframes
        df1 = pd.DataFrame(result1, columns=(['hash'] + resolve+[feature]))
        df2 = pd.DataFrame(result2, columns=(['hash'] + tmout))

        #check of dataframe values
        for replacement in replace_dict:
            for (key, value) in replace_dict[replacement]:
                df2.replace(key, value)

        df = df1.join(df2.set_index('hash'), on='hash')

        #delete hash column
        del df['hash']


        #delete unknown feature entries
        for i in range(len(df)):
            if df.at[i, feature] == 'unknown' or df.at[i, feature] == 'empty':
                df = df.drop(i)

        df = df.reset_index(drop=True)


        # convert to floats where possible
        for col in df.columns:
            for i in range(len(df)):
                e = df.iloc[i][col]

                if util.is_number(e):
                    # MI: does not belong here
                    if float(e).is_integer():
                        df.at[i, col] = int(float(e))
                    else:
                        df.at[i, col] = float(e)

        # return a dataframe that is as prepared for classification as possible
        return df