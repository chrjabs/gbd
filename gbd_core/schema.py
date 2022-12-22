# GBD Benchmark Database (GBD)
# Copyright (C) 2021 Markus Iser, Karlsruhe Institute of Technology (KIT)
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
import os
import csv
import re

from dataclasses import dataclass

from gbd_core import contexts
from gbd_core.util import eprint


class SchemaException(Exception):
    pass


@dataclass
class FeatureInfo:
    name: str = None
    database: str = None
    context: str = None
    table: str = None
    column: str = None
    default: str = None
    virtual: bool = False


class Schema:

    IN_MEMORY_DB_NAME = "in_memory"

    def __init__(self, dbname, path, features):
        self.dbname = dbname
        self.path = path
        self.features = features

    @classmethod
    def is_database(cls, path):
        if not os.path.isfile(path): 
            eprint("Creating Database {}".format(path))
            sqlite3.connect(path).close()
            return True
        sz = os.path.getsize(path)
        if sz == 0: return True  # new sqlite3 files can be empty
        if sz < 100: return False  # sqlite header is 100 bytes
        with open(path, 'rb') as fd: header = fd.read(100)  # validate header
        return (header[:16] == b'SQLite format 3\x00')

    @classmethod
    def create(cls, path):
        try:
            if cls.is_database(path):
                return cls.from_database(path)
            else:
                return cls.from_csv(path)
        except Exception as e:
            raise SchemaException(str(e))

    @classmethod
    def from_database(cls, path):
        dbname = cls.dbname_from_path(path)
        con = sqlite3.connect(path)
        features = cls.features_from_database(dbname, path, con)
        con.close()
        return cls(dbname, path, features)

    @classmethod
    def from_csv(cls, path):
        dbname = cls.IN_MEMORY_DB_NAME
        con = sqlite3.connect("file::memory:?cache=shared", uri=True)
        features = cls.features_from_csv(dbname, path, con)
        con.close()
        return cls(dbname, path, features)

    # Import CSV to in-memory db, create according schema info
    @classmethod
    def features_from_csv(cls, dbname, path, con):
        features = dict()
        with open(path) as csvfile:
            csvreader = csv.DictReader(csvfile)
            if "hash" in csvreader.fieldnames:
                vtable_name = Schema.dbname_from_path(path)
                cols = [ re.sub('[^0-9a-zA-Z]+', '_', n) for n in csvreader.fieldnames ]
                for colname in cols:
                    cls.valid_feature_or_raise(colname)
                    features[colname] = FeatureInfo(colname, dbname, contexts.context_from_name(colname), vtable_name, colname, None, True)
                con.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(vtable_name, ", ".join(cols)))
                for row in csvreader:
                    con.execute("INSERT INTO {} VALUES ('{}')".format(vtable_name, "', '".join(row.values())))
                con.commit()
            else:
                raise SchemaException("Column 'hash' not found in {}".format(csvfile))
        return features

    # Create schema info for sqlite database
    @classmethod
    def features_from_database(cls, dbname, path, con):
        features = dict()
        sql_tables="""SELECT tbl_name, type FROM sqlite_master WHERE type IN ('table', 'view') 
                        AND NOT tbl_name LIKE 'sqlite$_%' AND NOT tbl_name LIKE '$_$_%' ESCAPE '$'"""
        tables = con.execute(sql_tables).fetchall()
        # process features-table last to give precedence to features in other tables
        if ("features", "table") in tables:
            tables.insert(len(tables)-1, tables.pop(tables.index(("features", "table")))) 
        for (table, type) in tables:
            context = contexts.context_from_name(table)
            columns = con.execute("PRAGMA table_info({})".format(table)).fetchall()
            for (index, colname, coltype, notnull, default_value, pk) in columns:
                if not colname in [ tabname for (tabname, _) in tables ]:
                    fname = contexts.prepend_context("hash", context) if colname == "hash" else table if colname == "value" else colname
                    dval = default_value.strip('"') if default_value else None
                    features[fname] = FeatureInfo(fname, dbname, context, table, colname, dval, type == "view")
        return features

    @classmethod
    def dbname_from_path(cls, path):
        filename = os.path.basename(path)
        return re.sub("[^a-zA-Z0-9]", "_", filename)

    @classmethod
    def valid_feature_or_raise(cls, name):
        if len(name) < 2:
            raise SchemaException("Feature name '{}' is to short.".format(name))
        gbd_keywords = [ 'hash', 'value', 'local', 'filename', 'features' ]
        if name.lower() in gbd_keywords or name.startswith("__"):
            raise SchemaException("Feature name '{}' is reserved.".format(name))
        sqlite_keywords = ['abort', 'action', 'add', 'after', 'all', 'alter', 'always', 'analyze', 'and', 'as', 'asc', 'attach', 'autoincrement', 
            'before', 'begin', 'between', 'by', 'cascade', 'case', 'cast', 'check', 'collate', 'column', 'commit', 'conflict', 'constraint', 
            'create', 'cross', 'current', 'current_date', 'current_time', 'current_timestamp', 'database', 'default', 'deferrable', 'deferred', 
            'delete', 'desc', 'detach', 'distinct', 'do', 'drop', 'each', 'else', 'end', 'escape', 'except', 'exclude', 'exclusive', 'exists', 
            'explain', 'fail', 'filter', 'first', 'following', 'for', 'foreign', 'from', 'full', 'generated', 'glob', 'group', 'groups', 
            'having', 'if', 'ignore', 'immediate', 'in', 'index', 'indexed', 'initially', 'inner', 'insert', 'instead', 'intersect', 'into', 'is', 'isnull', 
            'join', 'key', 'last', 'left', 'like', 'limit', 'match', 'materialized', 'natural', 'no', 'not', 'nothing', 'notnull', 'null', 'nulls', 
            'of', 'offset', 'on', 'or', 'order', 'others', 'outer', 'over', 'partition', 'plan', 'pragma', 'preceding', 'primary', 'query', 
            'raise', 'range', 'recursive', 'references', 'regexp', 'reindex', 'release', 'rename', 'replace', 'restrict', 'returning', 'right', 'rollback', 
            'row', 'rows', 'savepoint', 'select', 'set', 'table', 'temp', 'temporary', 'then', 'ties', 'to', 'transaction', 'trigger', 'unbounded', 'union', 
            'unique', 'update', 'using', 'vacuum', 'values', 'view', 'virtual', 'when', 'where', 'window', 'with', 'without']
        if name.lower() in sqlite_keywords or name.startswith("sqlite_"):
            raise SchemaException("Feature name '{}' is reserved by sqlite.".format(name))

    def is_in_memory(self):
        return self.dbname == self.IN_MEMORY_DB_NAME

    def get_connection(self):
        if self.is_in_memory():
            return sqlite3.connect("file::memory:?cache=shared", uri=True)
        else:
            return sqlite3.connect(self.path)

    def execute(self, sql):
        con = self.get_connection()
        cur = con.cursor()
        cur.execute(sql)
        con.commit()
        con.close()

    def get_contexts(self):
        return list(set([ f.context for f in self.get_features() ]))

    def get_tables(self):
        return list(set([ f.table for f in self.get_features() ]))

    def get_views(self):
        return list(set([ f.table for f in self.get_features() if f.virtual ]))

    def get_features(self):
        return self.features.values()

    def has_feature(self, name):
        return name in self.features.keys()

    def absorb(self, schema):
        if self.is_in_memory() and schema.is_in_memory():
            self.features.update(schema.features)
        else:
            raise SchemaException("Internal Error: Attempt to merge non-virtual schemata")


    def create_context_main_table_if_not_exists(self, context):
        main_table = contexts.prepend_context("features", context)
        if not main_table in self.get_tables():
            self.execute("CREATE TABLE IF NOT EXISTS {} (hash UNIQUE NOT NULL)".format(main_table))
            # insert all known hashes into main table and create triggers
            for table in [ t for t in self.get_tables() if context == contexts.context_from_name(t) ]:
                self.execute("INSERT OR IGNORE INTO {} (hash) SELECT DISTINCT(hash) FROM {}".format(main_table, table))
                self.execute("""CREATE TRIGGER IF NOT EXISTS {}_dval AFTER INSERT ON {} 
                                            BEGIN INSERT OR IGNORE INTO {} (hash) VALUES (NEW.hash); END""".format(table, table, main_table))
            fhash = contexts.prepend_context("hash", context)
            self.features[fhash] = FeatureInfo(fhash, self.dbname, context, main_table, "hash", None, False)
            return [ self.features[fhash] ]
        else:
            return [ ]


    def create_feature(self, name, default_value=None, permissive=False):
        if not permissive:  # internal use can be unchecked, e.g., to create the reserved features during initialization
            Schema.valid_feature_or_raise(name)

        created = [ ]
        
        if not self.has_feature(name):
            # ensure existence of context's main table:
            context = contexts.context_from_name(name)
            created.extend(self.create_context_main_table_if_not_exists(context))

            # create new feature:
            context_main_table = contexts.prepend_context("features", context)
            self.execute('ALTER TABLE {} ADD {} TEXT NOT NULL DEFAULT {}'.format(context_main_table, name, default_value or "None"))
            if default_value is not None:
                # feature is unique and resides in main features-table:
                self.features[name] = FeatureInfo(name, self.dbname, context, context_main_table, name, default_value, False)
            else:
                # feature is not unique and resides in a separate table (column in main features-table is a foreign key):
                self.execute("CREATE TABLE IF NOT EXISTS {} (hash TEXT NOT NULL, value TEXT NOT NULL, CONSTRAINT all_unique UNIQUE(hash, value))".format(name))
                self.execute("INSERT INTO {} (hash, value) VALUES ('None', 'None')".format(name))
                self.execute("""CREATE TRIGGER IF NOT EXISTS {}_hash AFTER INSERT ON {}
                                    BEGIN INSERT OR IGNORE INTO {} (hash) VALUES (NEW.hash); END""".format(name, name, context_main_table))
                self.features[name] = FeatureInfo(name, self.dbname, context, name, "value", None, False)

            # update schema:
            created.append(self.features[name])

            # create default filename-views for local path features:
            if name == contexts.prepend_context("local", context):
                created.extend(self.create_filename_view(context))

        elif not permissive:
            raise SchemaException("Feature {} already exists".format(name))

        return created


    def create_filename_view(self, context):
        local = contexts.prepend_context("local", context)
        filename = contexts.prepend_context("filename", context)
        self.execute("CREATE VIEW IF NOT EXISTS {} (hash, value) AS SELECT hash, REPLACE(value, RTRIM(value, REPLACE(value, '/', '')), '') FROM {}".format(filename, local))
        self.features[filename] = FeatureInfo(filename, self.dbname, context, filename, "value", None, False)
        return [ self.features[filename] ]


    def set_values(self, feature, value, hashes):
        if not self.has_feature(feature):
            raise SchemaException("Feature {} does not exist".format(feature))

        table = self.features[feature].table
        column = self.features[feature].column
        values = ', '.join(["('{}', '{}')".format(hash, value) for hash in hashes])
        if not self.features[feature].default:
            context_main_table = contexts.prepend_context("features", contexts.context_from_name(feature))
            self.execute("INSERT OR IGNORE INTO {tab} (hash, {col}) VALUES {vals}".format(tab=table, col=column, vals=values))
            self.execute("UPDATE {tab} SET {col}=hash WHERE hash in ('{h}')".format(tab=context_main_table, col=table, h="', '".join(hashes)))
        else:
            self.execute("INSERT INTO {tab} (hash, {col}) VALUES {vals} ON CONFLICT (hash) DO UPDATE SET {col}='{val}' WHERE hash in ('{h}')".format(tab=table, col=column, val=value, vals=values, h="', '".join(hashes)))


    #migrate from old schema to new schema
    def create_foreign_key_columns(self, context):
        # create fk-column for multi-valued tables if they do not exist
        main_table = contexts.prepend_context("features", context)
        main_table_features = [ g.name for g in filter(lambda f: f.table == main_table, self.features) ]
        tables = [ t for t in self.get_tables() if context == contexts.context_from_name(t) and t != main_table ]
        missing = [ f for f in tables if f not in main_table_features ]
        con = self.get_connection()
        for feature in missing:
            con.execute('ALTER TABLE {} ADD {} TEXT NOT NULL DEFAULT {}'.format(main_table, feature, "None"))
            result = con.execute("SELECT DISTINCT hash FROM " + feature).fetchall()
            query = "UPDATE {} SET {} = ? WHERE hash = ?".format(main_table, feature)
            hashes = [ [h, h] for (h,) in result ]
            k = int(len(hashes) / 1000)
            for subl in [ hashes[i : i + k] for i in range(0, len(hashes), k) ]:
                con.executemany(query, subl)
                con.commit()
            con.execute("INSERT OR REPLACE INTO {} VALUES ('None', 'None')".format(feature))
            con.commit()
        con.close()            

    def create_context_translator_table(self, src, dst):
        translator = "{}_to_{}".format(src, dst)
        if not translator in self.get_tables():
            con = self.get_connection()
            con.execute("CREATE TABLE IF NOT EXISTS {} (hash, value)".format(translator))
            con.commit()
            con.close()
        fhash = contexts.prepend_context("hash", src)
        self.features[fhash] = FeatureInfo(fhash, self.dbname, src, translator, "hash", None, False)