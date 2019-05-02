# Developing in CourtListener

CourtListener is built upon a few key pieces of technology that needs to come together in order to function. Whether you're contributing platform code, web design, etc. it helps to know the easiest ways to run and test the project.

There are a few development options depending on your level of experience or comfort with a complex Django web application.

1. Configure your own Ubuntu Linux environment to support running CourtListener per the [wiki instructions][wiki]
2. Use [Vagrant](https://vagrantup.com) and [VirtualBox](https://virtualbox.org) to virtualize a CourtListener-ready Linux environment.

# Using Vagrant and VirtualBox

The recommended approach is to use the Vagrant box provided by the [FreeLawMachine][flm] project. It provides a standardized ready-to-run virtual machine, provisioned by Vagrant, pre-configured to provide:

* Ubuntu 14.04.5 64-bit
* PostgreSQL
* Apache Solr
* Redis, Celery, and other dependencies for OCR, etc.
* Python 2.7 virtual environment pre-installed with CourtListener requirements
* CourtListener github project precloned to `/var/www/courtlistener` (within the VM)

Install both [Vagrant](https://vagrantup.com) and [VirtualBox](https://virtualbox.org) and check the [FreeLawMachine README][flm-readme] before continuing.

Then, just choose one of the following boxes, grab the provided Vagrantfile, save it to a location to use for your project, and run `vagrant up`!


## Headless FreeLawBox
[Vagrantfile](https://github.com/freelawproject/freelawmachine/blob/master/Vagrantfile)

Preconfigured for:
* 2 CPU cores
* 2.5 GB of RAM
* 20 GB of disk space

This version works great for command-line access via `vagrant ssh`, using your own local IDE (emacs, Atom, PyCharm, etc.) and fully supports premium PyCharm features for seamless integration. It automatically activates the provided _courtlistener_ Python virtual environment upon login.

_Note: if using a tool like PyCharm that supports a remote Python interpreter, set it to: `/home/vagrant/.virtualenvs/courtlistener/bin/python` and make sure you set the working directory to `/var/www/courtlistener`. You may also need to prevent the tool from adding the project to the PYTHONPATH, which is not needed due to the virtual environment._

## Desktop/GUI-based FreeLawBox
[Vagrantfile][vagrantfile-desktop]

Preconfigured for:
* 2 CPU cores
* 4 GB of RAM
* 20 GB of disk space
* XFCE4-based desktop environment

This version will automatically log you into an XFCE4 desktop as the _vagrant_ user. When you open a terminal (or ssh into the machine via `vagrant ssh`) it will automatically activate the _courtlistener_ Python virtual environment.

# Running Django Tests

Any time you're contributing to or hacking on code base, whether adding features or fixing issues, you should validate your changes don't break the core functionality of CourtListener by executing the test suite. This is also a great way to validate your development environment is properly configured. (You should probably consider adding your own tests as well!)

In general, the easiest way to run the test suite is via Django's `test` command. An example from within the FreeLawBox images:

```bash
>(courtlistener)vagrant@freelawbox64:/var/www/courtlistener$ ./manage.py test --noinput cl
```

The `--noinput` flag tells Django to destroy any old test databases without prompting for confirmation (typically this is what you want).

The `cl` parameter is the name of the Python package to search for tests. It's not required, but a good habit to learn as you can more specifically specify tests by provided more details, such as `cl.search` to execute only tests in the search module.

For more details, Django provides a lot of documentation on [testing in Django][django-testing]. Make sure to read the docs related to the current release used in CourtListener. (As of 27-01-2017, that's v1.8.7.)

## About the Types of Tests

There are a few different types of tests in the CourtListener test suite and can be generally categorized as follows in increasing complexity:
* **Unit Tests** that exercise core application logic and may require some level of access to the Django test database,
* **Solr Tests** that rely on the Apache Solr test cores to be online and have documents indexed for test execution,
* **Selenium Tests** that rely on the full-stack of Django, the database, and Solr to be available in order to test from the point of view of a web browser accessing the application.

### Unit Tests

Unit tests should derive from `unittest.TestCase` or `django.test.TestCase` and run without a functioning Solr environment or Selenium functioning. These are the bread and butter of validating functions and business logic. You should contribute these when you write any new functions or update them when enhancing existing functions.

### Solr Tests

Solr/search tests should derive from `cl.search.tests.EmptySolrTestCase` and use appropriate setup/teardown methods to populate the index by either manually creating model instances and passing the `index=True` attribute when calling `.save()` or calling the provided `cl.search.management.commands.cl_update_index` Django management command that will index the models from the database into the Solr cores.

### Selenium Tests

Selenium tests should derive from `cl.tests.base.BaseSeleniumTest`, which automatically handles the setup and teardown of a Selenium webdriver instance available at `self.browser` from within your test code.

There are some helper methods provided via `BaseSeleniumTest` as well:
* `reset_browser()` - start a new browser session
* `click_link_for_new_page(link_text, timeout)` - a wrapper around the Selenium functions for finding an anchor based on the anchor text and calling click(), but also does an explicit wait up until _timeout_ seconds for the browser page to change. Use when expecting a navigation event.
* `attempt_sign_in(username, password)` - from a given CL page, will attempt to use the _Sign in / Register_ link and input the given username and password.
* `get_url_and_wait(url, timeout)` - will input the given url into the browser's address bar, submit, and wait until _timeout_ seconds for the given url to load.
* `assert_text_in_body(text)` - attempts to find the given text in the body of the current web page, failing the test if not found
* `assert_text_not_in_body(text)` - similar to previous, but tests that text is NOT in the body, failing if it's found.
* `extract_result_count_from_serp()` - if on the search result page, will attempt to find and parse the total results found count into a number and return it.

## Running the Test Suite

If you're going to run the full test suite, you might need to pre-configure some environment variables to assist in the Selenium test execution.

### Selenium Tests when Headless

If you're using the FreeLawMachine in headless mode (e.g. you only SSH into the machine, there's no visible desktop environment), you need to do a few additional steps to run the Selenium tests without fail:

1. Install [Chrome](https://google.com/chrome) or [Chromium](https://www.chromium.org) on your local machine
2. Install or upgrade [chromedriver][] on your local machine
3. Launch **chromedriver** either as a service or just from a command line. The following example will start it ready to receive input from any host:
    ```bash
    chromedriver --whitelisted-ips
    ```
4. In your FreeLawBox or similar VM, configure some environment properties. In Linux, you can use the `export` command like so: `export PROPERTY=value`
  * `DJANGO_LIVE_TEST_SERVER_ADDRESS=0.0.0.0:8081`
  * `SELENIUM_REMOTE_ADDRESS=10.0.2.2:9515`
5. Run the test suite as normal.

If the above is working, you should see Selenium use your local copy of Chrome/Chromium to run the tests (i.e. the one NOT in the VM but on your host laptop/desktop).

If you have issues, check the following:
* **SELENIUM_REMOTE_ADDRESS**
  * From within your VM, check for the gateway IP address. In Linux, run `netstat -r` and get the gateway IP from the routing table.
  * For the port number, make sure it matches the port number printed by **chromedriver** when you start it. The default should be `9515`
* **DJANGO_LIVE_TEST_SERVER_ADDRESS**
  * This should "just work" when set to `0.0.0.0:8081`. Make sure you didn't use `localhost` or `127.0.0.1` as for some reason that doesn't always work!
  * If you're not using the provided FreeLawBox, make sure you have port forwarding configured in your VM such that port 8081 is being forwarded to your host machine's port 8081. See the [vagrant port forwarding docs][vagrant-ports] for more details.

### Increasing the Test Timeouts

The Selenium tests are wrapped with a timeout annotation that will fail them if they take too long to run. If you need to increase, or even want to decrease, this value then the easiest step is to set the `SELENIUM_TIMEOUT` environment variable to the given time in seconds.

For example, for a 2 minute timeout, you might do the following on Linux (or within the FreeLawBox):

```bash
export SELENIUM_TIMEOUT=120
```

### Taking Screenshots on Failure

While a little flaky at the moment, most Selenium tests will be able to take a screenshot of the browser window on a failure. This should work well when running the FreeLawBox Desktop version (i.e. NOT in headless mode).

To enable screenshots, simply define a `SELENIUM_DEBUG` environment variable set to anything. It's presence indicates it's enabled.

```bash
export SELENIUM_DEBUG=1
```

You should find screenshot files available in the project directory. It's recommend you run the test suite with the `--failfast` option so it stops executing the rest of the tests if it encounters a failure. Currently, the screenshot is named after the test class and you may overwrite a screenshot if you continue through more tests in the same class.

## CI/CD

This Github project is configured to run tests for every pull request.
A webhook triggers [CircleCI][circleci-cl-builds] to run `.circleci/config.yml`.
`config.yml` makes CircleCI run tests inside a Docker container. The custom
Docker image used to run tests is built from `.circleci/Dockerfile` and pushed
to [Docker Hub][hub-cl-testing].

### Updating the testing container

If you add new dependencies, remember to update the testing container with the following steps.

1. Have `docker` and `make` CLI tools installed.
2. Have a Docker Hub account that's a member of the [freelawproject organization][hub-flp].
3. `docker login` with your credentials for the Hub account above.
4. Set the version in `version.txt` to whatever makes sense according to
   semantic versioning. Most of the time incrementing the patch version is enough.
   Also remove `-SNAPSHOT`.
5. `make push --file .circleci/Makefile` 
6. Use new Docker image in CircleCI tests by updating the [tag in config.yml][circleci-test-container-tag].
7. Wait for the build to finish, **then** increment `version.txt` and
   append `-SNAPSHOT` to the version string to prepare for the next SNAPSHOT
   release. This is to prevent someone from accidentally overwriting a stable
   release.


[wiki]: https://github.com/freelawproject/courtlistener/wiki/Installing-CourtListener-on-Ubuntu-Linux
[chromedriver]: https://sites.google.com/a/chromium.org/chromedriver/downloads
[django-testing]: https://docs.djangoproject.com/en/1.8/topics/testing/
[vagrantfile]: https://raw.githubusercontent.com/freelawproject/freelawmachine/master/Vagrantfile
[vagrantfile-desktop]: https://github.com/freelawproject/freelawmachine/blob/master/Vagrantfile.desktop
[flm]: https://github.com/freelawproject/freelawmachine
[flm-readme]: https://github.com/freelawproject/freelawmachine/blob/master/README.md
[vagrant-ports]: https://www.vagrantup.com/docs/networking/forwarded_ports.html
[circleci-cl-builds]: https://circleci.com/gh/freelawproject/courtlistener
[hub-cl-testing]: https://hub.docker.com/r/freelawproject/courtlistener-testing/
[hub-flp]: https://hub.docker.com/u/freelawproject/dashboard/
[circleci-test-container-tag]: https://github.com/freelawproject/courtlistener/blob/360c259f7d427700c2de9bf8fd53a73a33ff2eed/.circleci/config.yml#L5
