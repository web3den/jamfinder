# Mutation testing in a container, with the network switched off:
#   docker build -f qa/Dockerfile -t jamfinder-qa .
#   docker run --rm --network none jamfinder-qa
FROM python:3.12-slim
WORKDIR /repo
COPY requirements.txt pins/package.txt
COPY qa/requirements.txt pins/qa.txt
RUN pip install --no-cache-dir -r pins/package.txt -r pins/qa.txt
COPY . .
RUN useradd --create-home tester && chown -R tester /repo
USER tester
CMD ["python", "-m", "qa.mutation.mutate", "jf/rules.py", "tests/test_rules.py", \
     "qa/mutation/generated/test_rules_killers.py", "--min-score", "95"]
