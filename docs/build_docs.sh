#!/bin/bash

which python
which python3
which sphinx-build

if [ -n "$PYTHONUSERBASE" ]; then
  v=$(python3 -c "from sys import version_info as v ; print(f'{v[0]}.{v[1]}', end='')")
  export PYTHONPATH=$PYTHONUSERBASE/lib/python${v}/site-packages:$PYTHONPATH
fi

# Inform to the workflow visualization function that the
# notebooks are to be exported to html
export SISL_NODES_EXPORT_VIS=1

# Now ensure everything is ready...
make html
retval=$?

# If succeeded, we may overwrite the old
# documentation (if it exists)
if [ $retval -eq 0 ]; then
    echo "Success = $retval"
else
    echo "Failure = $retval"
fi
