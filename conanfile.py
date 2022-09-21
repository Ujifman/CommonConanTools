from conans import ConanFile, CMake, tools, RunEnvironment
import os
import re
from conans.model.requires import Requirements
from conans.errors import ConanException
from six import StringIO
from sys import platform


class CommonConanFile(ConanFile):
    name = "CommonConanFile"
    version = "0.12"


# =================================================================================================
# =================================================================================================

class NotCriticalException(Exception):
    pass

# =================================================================================================
# =================================================================================================


# Common ConanFile with common values and methods suitable for every MonitorSoft package
class AbstractConanFile(object):
    license = "MonitorSoft Limited"
    additional_includedirs = []  # Variable to add some more dirs than standard (src->include) to includepath

    def requirements_substitution(self, req_name):
        """
        Method for replacing dependencies channel from "stable" to "dev". It is used for complete replacement of channel
            for all dependencies including all transition dependencies.
        :param req_name: name of Conan requirement variable. Conan has to variables Conanfile.requires and
            Conanfile.build_requires. Logic is the same for both methods. T
        :return:
        """
        if req_name == "requires":
            req_tuple = self.requires
            print_text = "Requirements"
        elif req_name == "build_requires":
            req_tuple = self.build_requires
            print_text = "Build Requirements"
        else:
            raise Exception("Something bad happend during requirements manipulation")

        try:
            env_channel = os.getenv("OVERRIDE_CONAN_CHANNEL") or os.getenv("CONAN_CHANNEL") # CONAN_CHANNEL reserved by Conan, and lead to side effects, deprecated now
            if env_channel == "dev" or self.channel == "dev":
                print("\033[93m{1} Stable to Dev substitution for package: {0}".format(self.name, print_text))
                
                # Copying list from tuple
                req_list = []
                for dep in req_tuple:
                    req_list.append(str(req_tuple[dep]))
                req_tuple.clear()
                # Iterate all deps
                for dep in req_list:
                    current_requirement = dep.replace("monsoft/stable", "monsoft/dev")
                    print("\033[93m{1} set requirement: {0}".format(current_requirement, print_text))
                    if req_name == "requires":
                        self.requires(current_requirement)
                    elif req_name == "build_requires":
                        self.build_requires(current_requirement)
        except ConanException as err:
            print(f'\033[93m{print_text} Exception while channel override: {err}')

    def requirements(self):  # Redefine Conanfile method to implement custom logic.
        self.requirements_substitution("requires")

    def build_requirements(self):  # Redefine Conanfile method to implement custom logic.
        self.requirements_substitution("build_requires")

    def package(self):  # Redefine Conanfile method to implement custom logic.
        self.copy("*.h", src="src", dst="include")
        self.copy("*.hpp", src="src", dst="include")
        self.copy("*.ts", src="src", dst="translation", keep_path=False)
        self.copy("*", src="runtime", dst="runtime")
        self.copy("*.pri", src="qmake_pri", dst="build_modules")

        if os.getcwd() == self.build_folder:
            if "shared" in self.options.fields: # check if shared applicable
                if self.options.shared:
                    self.copy("*.dll", src=self.build_folder, dst="lib", keep_path=False)
                    self.copy("*.so*", src=self.build_folder, dst="lib", symlinks=True, keep_path=False)
                else:
                    self.copy("*{0}.lib".format(self.name), src=self.build_folder, dst="lib", keep_path=False)
                    self.copy("*.a", src=self.build_folder, dst="lib", keep_path=False)

    def package_info(self):
        # Combine full list of includedirs according to editable/not editable mode
        base_includedir = "include" if self.in_local_cache else "src"
        self.cpp_info.includedirs = [base_includedir] + \
                                    ["{0}/{1}".format(base_includedir, dir) for dir in self.additional_includedirs]


# =================================================================================================
# =================================================================================================


# ConanFile perfectly suitable for header only libraries, without build
class HeaderOnlyConanFile(AbstractConanFile):
    no_copy_source = True
    
    
# =================================================================================================
# =================================================================================================


# ConanFile perfectly suitable for library that hold common pri files
class QmakePriOnlyConanFile(AbstractConanFile):
    no_copy_source = True

    
# =================================================================================================
# =================================================================================================

   
# ConanFile suitable for packages that should be built
class BuildableConanFile(AbstractConanFile):
    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False],
               "qt_ver": ["5.5.1", "5.9.8", "5.13.2", "5.15.2", None],
               "unit_testing": [True, False],
               "with_coverage": [True, False],
               "sample": [True, False]}  # option for isolate sample deps
    buildable_type = None  # [ shared, static, app ]
    unit_test_executables = None # list of test executables
    run_tests_headless = True # variable to define if fake gui windos needed for tests running. Default is True
    cmake_definitions = {} # dict variable to customize CMake definitions before configure

    # default options. DO NOT CHANGE "== None" TO "is None". IT BREAKS LOGIC. "== None" and "is None" ARE NOT THE SAME.
    def config_options(self):  # Redefine Conanfile method to implement custom logic.
        if self.options.qt_ver == None:
            pass # It is default value
        if self.options.unit_testing == None:
            self.options.unit_testing = False
        if self.options.with_coverage == None:
            self.options.with_coverage = False
        if self.options.sample == None:
            self.options.sample = False

        if self.buildable_type == "shared":
            self.options.shared = True
        elif self.buildable_type == "static":
            self.options.shared = False
        elif self.buildable_type == "sample" or self.buildable_type == "app":
            del self.options.shared
        else:
            raise Exception("Buildable type not specified")

    def imports(self):  # Redefine Conanfile imports method to implement custom logic.
        # Copying pri files from build_modules dir
        self.copy("*.pri", src="build_modules", dst="build_modules")

    def build(self):
        """
        ConanFile Build method, actually do build or unit testing depending on options
        :return:
        """
        try:
            # CMake
            if self.generators == ["cmake"]:
                # UnitTesting
                if self.options.unit_testing:
                    raise NotCriticalException("Unit testing for CMake not available")
                # Build
                else:
                    cmake = CMake(self)
                    for definition_key in self.cmake_definitions:
                        cmake.definitions[definition_key] = self.cmake_definitions[definition_key]
                    cmake.configure()
                    cmake.build()
            # QMake
            elif self.generators == ["qmake"]:
                # UnitTesting
                if self.options.unit_testing:
                    # Check Environment
                    if not self.settings.build_type == "Debug":
                        raise Exception("Unit test available only for Debug builds")
                    elif tools.cross_building(self.settings):
                        raise Exception("Unit test not available for cross building")
                    elif not tools.os_info.is_linux and not tools.os_info.is_windows:
                        raise Exception("Unit test can be run only on linux or windows")
                    else:
                        self.output.warn("Unit Testing starts")
                        if self.unit_test_executables is None:
                            self.unit_test_executables = ["tst_{0}".format(self.name)]
                        QMakeHelper(self).run_unit_test(self.name, self.unit_test_executables, self.run_tests_headless)
                        self.coverage()
                # Build
                else:
                    QMakeHelper(self).build_project(self.name, self.options.with_coverage)
            # Unknown generator
            else:
                raise Exception("Problem in build method, unknown generator {0}".format(self.generators))
        except NotCriticalException as err:
            self.output.warn("Build terminated. Not critical Excepiton: " + str(err))
    
    def package_info(self):
        super(BuildableConanFile, self).package_info()  # Call parent package_info method
        self.cpp_info.libs = [self.name]
        if "shared" in self.options.fields and not self.options.shared:
            self.cpp_info.defines = ["{0}_STATICLIB".format(self.name.upper())]

    def coverage(self):
        if not tools.which("lcov") or not tools.which("genhtml"):
            raise Exception("Coverage tools missed")

        self.output.warn("Coverage utilities found")
        self.output.info("Capturing initial data...")
        self.run("lcov -c --initial --directory . --output-file test_initial.info")

        self.output.info("Capturing coverage data...")
        self.run("lcov -c --directory . --output-file test_coverage.info")

        self.output.info("Mixing coverage data...")
        self.run("lcov --add-tracefile test_initial.info --add-tracefile test_coverage.info --output-file test.info",
                 output=None)

        self.output.info("Filtering coverage data...")
        self.run("lcov -e test.info \"*" + self.name.lower() + "/*\" --output-file test.info", output=None)
        self.run("lcov -r test.info \"*moc_*\" --output-file test.info", output=None)
        self.run("lcov -r test.info \"*qrc_*\" --output-file test.info", output=None)
        self.run("lcov -r test.info \"*ui_*\" --output-file test.info", output=None)
        self.run("lcov -r test.info \"*test_package/*\" --output-file test.info", output=None)
        self.run("lcov -r test.info \"*test_private/*\" --output-file test.info", output=None)
        self.run("lcov -r test.info \"*test_unit/*\" --output-file test.info", output=None)

        self.output.info("Writing coverage report...")
        tools.mkdir("coverage")

        buf = StringIO()
        self.run("genhtml test.info --output-directory coverage", output=buf)
        pattern = re.compile(r"^\s*lines\.*:\s*(\d+\.\d+%)", re.MULTILINE)
        match = pattern.search(buf.getvalue())
        self.output.info("Total coverage: %s" % match.group(1))


# =================================================================================================
# =================================================================================================


# ConanFile for packages which are builded to StaticLibrary
class StaticLibConanFile(BuildableConanFile):
    buildable_type = "static"


# =================================================================================================
# =================================================================================================


# ConanFile for packages which are builded to DynamicLibrary
class DynamicLibConanFile(BuildableConanFile):
    buildable_type = "shared"

    def deploy(self):
        if "shared" in self.options.fields:  # check if shared applicable
            if self.options.shared:
                if self.settings.os == "Linux":
                    self.copy("*.so*", src="lib", dst="bin", symlinks=True, keep_path=False)
                    self.copy_deps("*.so*", src="lib", dst="bin", keep_path=False)

                if self.settings.os == "Windows":
                    self.copy("*.dll", src="lib", dst="bin", keep_path=False)
                    self.copy_deps("*.dll", src="lib", dst="bin", keep_path=False)

                self.copy("*", src="runtime", dst="bin")
                self.copy_deps("*", src="runtime", dst="bin")


# =================================================================================================
# =================================================================================================


# ConanFile for packages which are builded to Full Application
class ApplicationConanFile(BuildableConanFile):
    buildable_type = "app"

# =================================================================================================
# =================================================================================================

# QMake build helper


class RelationConfigItem(object):
    relation = None  # type: str
    configs = []  # type: list

    def __init__(self, relation, configs):
        """
        :param relation:
        :type relation str
        :param configs:
        :type configs list
        """
        self.relation = relation
        self.configs = configs

    def __nonzero__(self):
        return len(self.configs) > 0

    def __bool__(self):
        return self.__nonzero__()


class QMakeParametersBuilder(object):
    qmake_var_name = None  # type: String
    append_keys = {}  # don't fill here
    remove_keys = {}  # don't fill here

    def __init__(self, conanfile):
        os_current = "os={0}".format(conanfile.settings.os)
        self.append_keys_current = []
        self.remove_keys_current = []

        if "all" in self.append_keys:
            self.append_keys_current.extend(self.append_keys["all"])
        if "all" in self.remove_keys:
            self.remove_keys_current.extend(self.remove_keys["all"])

        if os_current in self.append_keys:
            self.append_keys_current.extend(self.append_keys[os_current])
        if os_current in self.remove_keys:
            self.remove_keys_current.extend(self.remove_keys[os_current])

    def add_special_case_parameters(self, tag):
        """
        Adds special case command line parameters from builder append and remove keys to current applicable lists
        :param tag: dict key to take parameters
        :return:
        """
        if tag in self.append_keys:
            self.append_keys_current.extend(self.append_keys[tag])
        if tag in self.remove_keys:
            self.remove_keys_current.extend(self.remove_keys[tag])

    def _decorate_str(self, relation, key):
        if relation not in ["+=", "-="]:
            raise Exception("Relation must be += or -=")
        return "\"" + " ".join([self.qmake_var_name, relation, key]) + "\""

    @staticmethod
    def _decorate_configs_list(configs_list):
        return " ".join(configs_list)

    def build_parameters_string(self):
        keys = filter(lambda config_item: bool(config_item),
                      [RelationConfigItem("+=", self.append_keys_current),
                       RelationConfigItem("-=", self.remove_keys_current)])

        return " ".join(map(lambda config_item: self._decorate_str(config_item.relation,
                                                                   QMakeConfigBuilder._decorate_configs_list(
                                                                        config_item.configs)
                                                                   ), keys))


#
class QMakeConfigBuilder(QMakeParametersBuilder):
    qmake_var_name = "CONFIG"
    append_keys = {"all": ["skip_target_version_ext",
                           "conan_exported"]}
    remove_keys = {"all": ["debug_and_release",
                           "debug_and_release_target"]}


#
class QMakeCxxFlagsBuilder(QMakeParametersBuilder):
    qmake_var_name = "QMAKE_CXXFLAGS"
    append_keys = {"os=Linux": ["-Wno-expansion-to-defined",
                                "-Wno-deprecated",
                                "-Wno-reorder",
                                "-Wno-missing-field-initializers"],
                   "coverage": ["-g",
                                "-fprofile-arcs",
                                "-ftest-coverage",
                                "-O0"]}
    remove_keys = {}


#
class QMakeLibBuilder(QMakeParametersBuilder):
    qmake_var_name = "LIBS"
    append_keys = {"coverage": ["-lgcov"]}
    remove_keys = {}


#
class QMakeCFlagsBuilder(QMakeParametersBuilder):
    qmake_var_name = "QMAKE_CFLAGS"
    append_keys = {"coverage": ["-g",
                                "-fprofile-arcs",
                                "-ftest-coverage",
                                "-O0"]}
    remove_keys = {}


class QMakeHelper(object):
    """
    A class used to build QMake-based projects
    """

    conanfile = None # type: ConanFile

    def __init__(self, conanfile):
        """
        :param conanfile:
        :type conanfile: ConanFile
        """
        self.conanfile = conanfile
        self._make_program = tools.get_env("CONAN_MAKE_PROGRAM", "make")
    
    def get_version_str(self):
        build_id = tools.get_env("CI_PIPELINE_ID", "0")
        version_str = ""
        if self.conanfile.version is not None:
            if self.conanfile.version.count('.') == 2:
                version_str = '"VERSION = ' + self.conanfile.version + "." + build_id + '"'
            else:
                version_str = '"VERSION = ' + self.conanfile.version + '"'
        return version_str

    def clean(self):
        self.conanfile.run(self._make_program + " clean")

    def build(self, project_filename, with_clean=False, with_coverage=False):
        """
        Builds a .pro file

        :param project_filename:
        :param with_clean:
        :param with_coverage: add command line paramters to qmake to add tests coverage
        :return:
        """

        list_builders = []

        configs_builder = QMakeConfigBuilder(conanfile=self.conanfile)
        cxxflags_builder = QMakeCxxFlagsBuilder(conanfile=self.conanfile)

        list_builders.append(configs_builder)
        list_builders.append(cxxflags_builder)

        if "build_type" not in self.conanfile.settings.fields:
            self.conanfile.output.warn("build_type was not specified! Using debug!")
            configs_builder.append_keys_current.append("debug")
        else:
            configs_builder.append_keys_current.append("release" if str(self.conanfile.settings.build_type) == "Release"
                                                      else "debug")
        if "shared" in self.conanfile.options.fields and not self.conanfile.options.shared:
            configs_builder.append_keys_current.append("staticlib")

        if with_coverage:
            cxxflags_builder.add_special_case_parameters("coverage")

            lib_builder = QMakeLibBuilder(conanfile=self.conanfile)
            lib_builder.add_special_case_parameters("coverage")
            cflags_builder = QMakeCFlagsBuilder(conanfile=self.conanfile)
            cflags_builder.add_special_case_parameters("coverage")

            list_builders.append(lib_builder)
            list_builders.append(cflags_builder)

        qmake_command = " ".join([
            "qmake",
            " ".join([builder.build_parameters_string() for builder in list_builders]),
            self.get_version_str(),
            os.sep.join([self.conanfile.source_folder, project_filename])
        ])

        self.conanfile.output.info("QMake command: " + qmake_command)

        self.conanfile.run(qmake_command)
        self.conanfile.run(self._make_program + " -j" + str(tools.cpu_count()))

        if with_clean:
            self.clean()

    def build_project(self, project_name, with_coverage=False):
        self.build(project_name + ".pro", with_clean=False, with_coverage=with_coverage)

    def build_unit_test(self, project_name):
        legacy_filename = project_name + "_TestPrivate.pro"
        modern_filename = project_name + "_TestUnit.pro"

        if os.path.isfile(os.sep.join([self.conanfile.source_folder, legacy_filename])):
            self.build(legacy_filename, True, True)
        elif os.path.isfile(os.sep.join([self.conanfile.source_folder, modern_filename])):
            self.build(modern_filename, True, True)
        else:
            raise NotCriticalException("No Unit tests project file found")

    def run_unit_test(self, project_name, test_executable_name=None, is_headless=True):
        """
        Function that builds and runs unit tests one by one
        :param project_name: Project name needed to define .pro file for building
        :param test_executable_name: list of executables or just name of on executable for running.
        :param is_headless:
        :return:
        """
        if test_executable_name is None:
            self.conanfile.output.info("Generate unit test executable name")
            test_executable_name = ["tst_" + project_name]
        elif not isinstance(test_executable_name, list):
            self.conanfile.output.info("Wrap unit test executable in list")
            test_executable_name = [test_executable_name]

        self.build_unit_test(project_name)
        self.conanfile.output.info("Unit test building finished")
        env_build = RunEnvironment(self.conanfile)

        prefix = ""
        postfix = ""
        if is_headless is True and platform in [ "linux", "linux2", "darwin" ]:
            prefix = "xvfb-run --server-args='-screen 0 640x480x24'"
            postfix = "-platform minimal"

        with tools.environment_append(env_build.vars):
            for current_test_executable in test_executable_name:
                run_command = " ".join([
                    prefix,
                    os.sep.join([".", current_test_executable]),
                    postfix
                ])
                self.conanfile.output.info("Run test command: " + run_command)
                self.conanfile.run(run_command)

