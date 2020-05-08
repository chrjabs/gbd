FROM python:3.7-alpine
COPY . /
RUN pip install 'global-benchmark-database-tool==2.7.6'
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8
EXPOSE 5000
WORKDIR .
ENTRYPOINT ["gbd-server"]
