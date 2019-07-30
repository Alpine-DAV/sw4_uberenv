# Copyright 2013-2019 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack import *

import sys
import os
import socket
import glob
import shutil

import llnl.util.tty as tty
from os import environ as env


def cmake_cache_entry(name, value, vtype=None):
    """
    Helper that creates CMake cache entry strings used in
    'host-config' files.
    """
    if vtype is None:
        if value == "ON" or value == "OFF":
            vtype = "BOOL"
        else:
            vtype = "PATH"
    return 'set({0} "{1}" CACHE {2}"")\n\n'.format(name, value, vtype)

def make_entry(name, value):
    return '{0} = {1} \n'.format(name, value)

def make_lib_entry(value):
    return ' -L {0}/lib/'.format(value)

def make_inc_entry(value):
    return ' -I{0}/include/'.format(value)

class UberenvSw4(Package):
    """Ascent is an open source many-core capable lightweight in situ
    visualization and analysis infrastructure for multi-physics HPC
    simulations."""

    homepage = "https://github.com/Alpine-DAV/sw4"
    git      = "https://github.com/Alpine-DAV/sw4.git"

    maintainers = ['mclarsen']

    version('develop',
            branch='ascent',
            submodules=True)

    ###########################################################################
    # package variants
    ###########################################################################

    variant("shared", default=True, description="Build Ascent as shared libs")
    variant("mpi", default=True, description="Build Ascent MPI Support")

    variant("cuda", default=True, description="Build cuda support")

    ###########################################################################
    # package dependencies
    ###########################################################################

    depends_on("proj@5.0.1")
    depends_on("blas")
    depends_on("netlib-lapack@3.8.0")

    depends_on("umpire@0.3.3+cuda")
    depends_on("raja@0.7.0+cuda", when="+cuda")

    #depends_on("cmake@3.9.2:3.9.999", type='build')
    #depends_on("conduit+python", when="+python+shared")

    #######################
    # MPI
    #######################
    depends_on("mpi", when="+mpi")

    #############################
    # TPLs for Runtime Features
    #############################


    def setup_environment(self, spack_env, run_env):
        spack_env.set('CTEST_OUTPUT_ON_FAILURE', '1')

    def install(self, spec, prefix):
        """
        Build and install Ascent.
        """
        with working_dir('spack-build', create=True):
                host_cfg_fname = self.create_host_config(spec, prefix)
                make_cfg_fname = self.makefile_inc(spec, prefix)
                # place a copy in the spack install dir for the uberenv-conduit package
                mkdirp(prefix)
                install(make_cfg_fname,prefix)
                install(host_cfg_fname,prefix)
                install(host_cfg_fname,env["SPACK_DEBUG_LOG_DIR"])
                install(make_cfg_fname,env["SPACK_DEBUG_LOG_DIR"])

    @run_after('install')
    @on_package_attributes(run_tests=True)
    def check_install(self):
        """
        Checks the spack install of ascent using ascents's
        using-with-cmake example
        """
        print("Checking Ascent installation...")
        spec = self.spec
        install_prefix = spec.prefix
        example_src_dir = join_path(install_prefix,
                                    "examples",
                                    "ascent",
                                    "using-with-cmake")
        print("Checking using-with-cmake example...")
        with working_dir("check-ascent-using-with-cmake-example",
                         create=True):
            cmake_args = ["-DASCENT_DIR={0}".format(install_prefix),
                          "-DCONDUIT_DIR={0}".format(spec['conduit'].prefix),
                          "-DVTKM_DIR={0}".format(spec['vtkm'].prefix),
                          "-DVTKH_DIR={0}".format(spec['vtkh'].prefix),
                          example_src_dir]
            cmake(*cmake_args)
            make()
            example = Executable('./ascent_render_example')
            example()
        print("Checking using-with-make example...")
        example_src_dir = join_path(install_prefix,
                                    "examples",
                                    "ascent",
                                    "using-with-make")
        example_files = glob.glob(join_path(example_src_dir, "*"))
        with working_dir("check-ascent-using-with-make-example",
                         create=True):
            for example_file in example_files:
                shutil.copy(example_file, ".")
            make("ASCENT_DIR={0}".format(install_prefix))
            example = Executable('./ascent_render_example')
            example()

    def create_host_config(self, spec, prefix, py_site_pkgs_dir=None):
        """
        This method creates a 'host-config' file that specifies
        all of the options used to configure and build ascent.

        For more details about 'host-config' files see:
            http://ascent.readthedocs.io/en/latest/BuildingAscent.html

        Note:
          The `py_site_pkgs_dir` arg exists to allow a package that
          subclasses this package provide a specific site packages
          dir when calling this function. `py_site_pkgs_dir` should
          be an absolute path or `None`.

          This is necessary because the spack `site_packages_dir`
          var will not exist in the base class. For more details
          on this issue see: https://github.com/spack/spack/issues/6261
        """

        #######################
        # Compiler Info
        #######################
        c_compiler = env["SPACK_CC"]
        cpp_compiler = env["SPACK_CXX"]
        f_compiler = None

        if self.compiler.fc:
            # even if this is set, it may not exist so do one more sanity check
            f_compiler = which(env["SPACK_FC"])

        #######################################################################
        # By directly fetching the names of the actual compilers we appear
        # to doing something evil here, but this is necessary to create a
        # 'host config' file that works outside of the spack install env.
        #######################################################################

        sys_type = spec.architecture
        # if on llnl systems, we can use the SYS_TYPE
        if "SYS_TYPE" in env:
            sys_type = env["SYS_TYPE"]

        ##############################################
        # Find and record what CMake is used
        ##############################################

        if "+cmake" in spec:
            cmake_exe = spec['cmake'].command.path
        else:
            cmake_exe = which("cmake")
            if cmake_exe is None:
                msg = 'failed to find CMake (and cmake variant is off)'
                raise RuntimeError(msg)
            cmake_exe = cmake_exe.path

        host_cfg_fname = "%s-%s-%s-ascent.cmake" % (socket.gethostname(),
                                                    sys_type,
                                                    spec.compiler)

        cfg = open(host_cfg_fname, "w")
        cfg.write("##################################\n")
        cfg.write("# spack generated host-config\n")
        cfg.write("##################################\n")
        cfg.write("# {0}-{1}\n".format(sys_type, spec.compiler))
        cfg.write("##################################\n\n")

        # Include path to cmake for reference
        cfg.write("# cmake from spack \n")
        cfg.write("# cmake executable path: %s\n\n" % cmake_exe)

        #######################
        # Compiler Settings
        #######################
        cfg.write("#######\n")
        cfg.write("# using %s compiler spec\n" % spec.compiler)
        cfg.write("#######\n\n")
        cfg.write("# c compiler used by spack\n")
        cfg.write(cmake_cache_entry("CMAKE_C_COMPILER", c_compiler))
        cfg.write("# cpp compiler used by spack\n")
        cfg.write(cmake_cache_entry("CMAKE_CXX_COMPILER", cpp_compiler))

        # shared vs static libs
        if "+shared" in spec:
            cfg.write(cmake_cache_entry("BUILD_SHARED_LIBS", "ON"))
        else:
            cfg.write(cmake_cache_entry("BUILD_SHARED_LIBS", "OFF"))

        #######################
        # Unit Tests
        #######################
        if "+test" in spec:
            cfg.write(cmake_cache_entry("ENABLE_TESTS", "ON"))
        else:
            cfg.write(cmake_cache_entry("ENABLE_TESTS", "OFF"))

        #######################################################################
        # Core Dependencies
        #######################################################################

        #######################
        # Conduit
        #######################

        cfg.write("# conduit from spack \n")
        cfg.write(cmake_cache_entry("LAPACK_DIR", spec['netlib-lapack'].prefix))
        cfg.write(cmake_cache_entry("BLAS_DIR", spec['blas'].prefix))
        cfg.write(cmake_cache_entry("UMPIRE_DIR", spec['umpire'].prefix))
        cfg.write(cmake_cache_entry("UMPIRE_DIR", spec['umpire'].prefix))

        #######################################################################
        # Optional Dependencies
        #######################################################################

        #######################
        # MPI
        #######################

        cfg.write("# MPI Support\n")

        if "+mpi" in spec:
            cfg.write(cmake_cache_entry("ENABLE_MPI", "ON"))
            cfg.write(cmake_cache_entry("MPI_C_COMPILER", spec['mpi'].mpicc))
            cfg.write(cmake_cache_entry("MPI_CXX_COMPILER",
                                        spec['mpi'].mpicxx))
            cfg.write(cmake_cache_entry("MPI_Fortran_COMPILER",
                                        spec['mpi'].mpifc))
            mpiexe_bin = join_path(spec['mpi'].prefix.bin, 'mpiexec')
            if os.path.isfile(mpiexe_bin):
                # starting with cmake 3.10, FindMPI expects MPIEXEC_EXECUTABLE
                # vs the older versions which expect MPIEXEC
                if self.spec["cmake"].satisfies('@3.10:'):
                    cfg.write(cmake_cache_entry("MPIEXEC_EXECUTABLE",
                                                mpiexe_bin))
                else:
                    cfg.write(cmake_cache_entry("MPIEXEC",
                                                mpiexe_bin))
        else:
            cfg.write(cmake_cache_entry("ENABLE_MPI", "OFF"))

        #######################
        # CUDA
        #######################

        cfg.write("# CUDA Support\n")

        if "+cuda" in spec:
            cfg.write(cmake_cache_entry("ENABLE_CUDA", "ON"))
        else:
            cfg.write(cmake_cache_entry("ENABLE_CUDA", "OFF"))

        if "+openmp" in spec:
            cfg.write(cmake_cache_entry("ENABLE_OPENMP", "ON"))
        else:
            cfg.write(cmake_cache_entry("ENABLE_OPENMP", "OFF"))

        cfg.write("##################################\n")
        cfg.write("# end spack generated host-config\n")
        cfg.write("##################################\n")
        cfg.close()

        host_cfg_fname = os.path.abspath(host_cfg_fname)
        tty.info("spack generated conduit host-config file: " + host_cfg_fname)
        return host_cfg_fname

    def makefile_inc(self, spec, prefix, py_site_pkgs_dir=None):
        """
        This method creates a 'make.inc' file that specifies
        all of the options used to configure and build sw4.
        """

        #######################
        # Compiler Info
        #######################
        c_compiler = env["SPACK_CC"]
        cpp_compiler = env["SPACK_CXX"]
        f_compiler = None

        if self.compiler.fc:
            # even if this is set, it may not exist so do one more sanity check
            f_compiler = which(env["SPACK_FC"])

        #######################################################################
        # By directly fetching the names of the actual compilers we appear
        # to doing something evil here, but this is necessary to create a
        # 'host config' file that works outside of the spack install env.
        #######################################################################

        sys_type = spec.architecture
        # if on llnl systems, we can use the SYS_TYPE
        if "SYS_TYPE" in env:
            sys_type = env["SYS_TYPE"]

        ##############################################
        # Find and record what CMake is used
        ##############################################

        host_cfg_fname = "make-%s-%s-%s-ascent.inc" % (socket.gethostname(),
                                                       sys_type,
                                                       spec.compiler)

        cfg = open(host_cfg_fname, "w")
        cfg.write("##################################\n")
        cfg.write("# spack generated make.inc\n")
        cfg.write("##################################\n")
        cfg.write("# {0}-{1}\n".format(sys_type, spec.compiler))
        cfg.write("##################################\n\n")

        #######################
        # Compiler Settings
        #######################
        cfg.write("#######\n")
        cfg.write("# using %s compiler spec\n" % spec.compiler)
        cfg.write("#######\n\n")
        cfg.write("# c compiler used by spack\n")
        cfg.write(make_entry("CC", c_compiler))
        cfg.write("# cpp compiler used by spack\n")
        #cfg.write(make_entry("CXX", cpp_compiler))
        cfg.write(make_entry("CXX", spec['mpi'].mpicxx))
        cfg.write("# fortran compiler used by spack\n")
        cfg.write(make_entry("FC", f_compiler))
        cfg.write(make_entry("CC", spec['mpi'].mpicxx))
        #cfg.write(make_entry("LINKER", spec['mpi'].mpicxx))
        cfg.write(make_entry("LINKER", "nvcc"))

        #######################
        # make cxx flags
        #######################
        cfg.write("EXTRA_CXX_FLAGS = ")
        # LAPACK
        cfg.write(make_inc_entry(spec['netlib-lapack'].prefix))
        # BLAS
        cfg.write(make_inc_entry(spec['blas'].prefix))
        # umpire
        cfg.write(make_inc_entry(spec['umpire'].prefix))
        # raja
        cfg.write(make_inc_entry(spec['raja'].prefix))
        # proj
        cfg.write(make_inc_entry(spec['proj'].prefix))
        cfg.write(" -DSW4_USE_UMPIRE=1 -DSW4_RAJA_VERSION=7")
        cfg.write(" -std=c++11")


        cfg.write(' -ccbin {0}'.format(spec['mpi'].mpicxx))
        cfg.write(' -Xcompiler \"-fopenmp\"'.format(spec['mpi'].mpicxx))
        cfg.write("\n")

        #######################
        # make link flags
        #######################
        cfg.write("EXTRA_LINK_FLAGS = ")
        # LAPACK
        cfg.write(make_lib_entry(spec['netlib-lapack'].prefix))
        # BLAS
        cfg.write(make_lib_entry(spec['blas'].prefix))
        # umpire
        cfg.write(make_lib_entry(spec['umpire'].prefix))
        # raja
        cfg.write(make_lib_entry(spec['raja'].prefix))
        # proj
        cfg.write(make_lib_entry(spec['proj'].prefix))
        cfg.write("\n")

        #cfg.write("# CUDA Support\n")

        #if "+cuda" in spec:
        #    cfg.write(cmake_cache_entry("ENABLE_CUDA", "ON"))
        #else:
        #    cfg.write(cmake_cache_entry("ENABLE_CUDA", "OFF"))

        #if "+openmp" in spec:
        #    cfg.write(cmake_cache_entry("ENABLE_OPENMP", "ON"))
        #else:
        #    cfg.write(cmake_cache_entry("ENABLE_OPENMP", "OFF"))

        cfg.write("##################################\n")
        cfg.write("# end spack generated make.inc\n")
        cfg.write("##################################\n")
        cfg.close()

        host_cfg_fname = os.path.abspath(host_cfg_fname)
        tty.info("spack generated conduit make.inc file: " + host_cfg_fname)
        return host_cfg_fname

    def create_host_config(self, spec, prefix, py_site_pkgs_dir=None):
        """
        This method creates a 'host-config' file that specifies
        all of the options used to configure and build ascent.

        For more details about 'host-config' files see:
            http://ascent.readthedocs.io/en/latest/BuildingAscent.html

        Note:
          The `py_site_pkgs_dir` arg exists to allow a package that
          subclasses this package provide a specific site packages
          dir when calling this function. `py_site_pkgs_dir` should
          be an absolute path or `None`.

          This is necessary because the spack `site_packages_dir`
          var will not exist in the base class. For more details
          on this issue see: https://github.com/spack/spack/issues/6261
        """

        #######################
        # Compiler Info
        #######################
        c_compiler = env["SPACK_CC"]
        cpp_compiler = env["SPACK_CXX"]
        f_compiler = None

        if self.compiler.fc:
            # even if this is set, it may not exist so do one more sanity check
            f_compiler = which(env["SPACK_FC"])

        #######################################################################
        # By directly fetching the names of the actual compilers we appear
        # to doing something evil here, but this is necessary to create a
        # 'host config' file that works outside of the spack install env.
        #######################################################################

        sys_type = spec.architecture
        # if on llnl systems, we can use the SYS_TYPE
        if "SYS_TYPE" in env:
            sys_type = env["SYS_TYPE"]

        ##############################################
        # Find and record what CMake is used
        ##############################################

        if "+cmake" in spec:
            cmake_exe = spec['cmake'].command.path
        else:
            cmake_exe = which("cmake")
            if cmake_exe is None:
                msg = 'failed to find CMake (and cmake variant is off)'
                raise RuntimeError(msg)
            cmake_exe = cmake_exe.path

        host_cfg_fname = "%s-%s-%s-ascent.cmake" % (socket.gethostname(),
                                                    sys_type,
                                                    spec.compiler)

        cfg = open(host_cfg_fname, "w")
        cfg.write("##################################\n")
        cfg.write("# spack generated host-config\n")
        cfg.write("##################################\n")
        cfg.write("# {0}-{1}\n".format(sys_type, spec.compiler))
        cfg.write("##################################\n\n")

        # Include path to cmake for reference
        cfg.write("# cmake from spack \n")
        cfg.write("# cmake executable path: %s\n\n" % cmake_exe)

        #######################
        # Compiler Settings
        #######################
        cfg.write("#######\n")
        cfg.write("# using %s compiler spec\n" % spec.compiler)
        cfg.write("#######\n\n")
        cfg.write("# c compiler used by spack\n")
        cfg.write(cmake_cache_entry("CMAKE_C_COMPILER", c_compiler))
        cfg.write("# cpp compiler used by spack\n")
        cfg.write(cmake_cache_entry("CMAKE_CXX_COMPILER", cpp_compiler))

        # shared vs static libs
        if "+shared" in spec:
            cfg.write(cmake_cache_entry("BUILD_SHARED_LIBS", "ON"))
        else:
            cfg.write(cmake_cache_entry("BUILD_SHARED_LIBS", "OFF"))

        #######################
        # Unit Tests
        #######################
        if "+test" in spec:
            cfg.write(cmake_cache_entry("ENABLE_TESTS", "ON"))
        else:
            cfg.write(cmake_cache_entry("ENABLE_TESTS", "OFF"))

        #######################################################################
        # Core Dependencies
        #######################################################################

        #######################
        # Conduit
        #######################

        cfg.write("# conduit from spack \n")
        cfg.write(cmake_cache_entry("LAPACK_DIR", spec['netlib-lapack'].prefix))
        cfg.write(cmake_cache_entry("BLAS_DIR", spec['blas'].prefix))
        cfg.write(cmake_cache_entry("UMPIRE_DIR", spec['umpire'].prefix))
        cfg.write(cmake_cache_entry("UMPIRE_DIR", spec['umpire'].prefix))

        #######################################################################
        # Optional Dependencies
        #######################################################################

        #######################
        # MPI
        #######################

        cfg.write("# MPI Support\n")

        if "+mpi" in spec:
            cfg.write(cmake_cache_entry("ENABLE_MPI", "ON"))
            cfg.write(cmake_cache_entry("MPI_C_COMPILER", spec['mpi'].mpicc))
            cfg.write(cmake_cache_entry("MPI_CXX_COMPILER",
                                        spec['mpi'].mpicxx))
            cfg.write(cmake_cache_entry("MPI_Fortran_COMPILER",
                                        spec['mpi'].mpifc))
            mpiexe_bin = join_path(spec['mpi'].prefix.bin, 'mpiexec')
            if os.path.isfile(mpiexe_bin):
                # starting with cmake 3.10, FindMPI expects MPIEXEC_EXECUTABLE
                # vs the older versions which expect MPIEXEC
                if self.spec["cmake"].satisfies('@3.10:'):
                    cfg.write(cmake_cache_entry("MPIEXEC_EXECUTABLE",
                                                mpiexe_bin))
                else:
                    cfg.write(cmake_cache_entry("MPIEXEC",
                                                mpiexe_bin))
        else:
            cfg.write(cmake_cache_entry("ENABLE_MPI", "OFF"))

        #######################
        # CUDA
        #######################

        cfg.write("# CUDA Support\n")

        if "+cuda" in spec:
            cfg.write(cmake_cache_entry("ENABLE_CUDA", "ON"))
        else:
            cfg.write(cmake_cache_entry("ENABLE_CUDA", "OFF"))

        if "+openmp" in spec:
            cfg.write(cmake_cache_entry("ENABLE_OPENMP", "ON"))
        else:
            cfg.write(cmake_cache_entry("ENABLE_OPENMP", "OFF"))

        cfg.write("##################################\n")
        cfg.write("# end spack generated host-config\n")
        cfg.write("##################################\n")
        cfg.close()

        host_cfg_fname = os.path.abspath(host_cfg_fname)
        tty.info("spack generated conduit host-config file: " + host_cfg_fname)
        return host_cfg_fname
