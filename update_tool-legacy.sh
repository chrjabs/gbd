sudo python3 setup-legacy.py develop sdist bdist_wheel
twine upload dist/*
sudo rm -Rf global_benchmark_database_tool.egg-info dist build
