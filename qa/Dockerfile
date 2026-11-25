# Mutation testing in a container, with the network switched off:
#   docker build -f qa/Dockerfile -t jamfinder-qa .
#   docker run --rm --network none jamfinder-qa
FROM python:3.12-slim
WORKDIR /repo
COPY requirements.txt qa/requirements.txt ./pins/
RUN pip install --no-cache-dir -r pins/requirements.txt && \
    pip install --no-cache-dir hypothesis==6.170.17 pymap3d==3.2.0 coverage==7.17.5
COPY . .
RUN useradd --create-home tester && chown -R tester /repo
USER tester
CMD ["python", "-m", "qa.mutation.mutate", "jf/rules.py", "tests/test_rules.py", \
     "qa/mutation/generated/test_rules_killers.py", "--min-score", "95"]
