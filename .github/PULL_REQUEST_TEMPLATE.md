## Fixes

What bugs does this fix? Use the syntax to auto-close the issue:

https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue#linking-a-pull-request-to-an-issue-using-a-keyword

E.g.: "Fixes: #XYZ"


## Summary

What does this fix, how did you fix it, what approach did you take, what gotchas are there in your code or compromises did you make?


## Deployment

<details>
<summary>Instructions</summary>

---

The following labels control the deployment of this PR if they’re applied. Please choose which should be applied, then apply them to this PR:

| Label                  | Description                             | Use case                                                                                                                         |
|------------------------|-----------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| `skip-deploy`          | The entire deployment can be skipped.   | This might be the case for a small fix, a tweak to documentation or something like that.                                         |
| `skip-web-deploy`      | The web tier can be skipped.            | This is the case if you're working on code that doesn't affect the front end, like management commands, tasks, or documentation. |
| `skip-celery-deploy`   | Deployment to celery can be skipped.    | This is the case if you make no changes to tasks.py or the code that tasks rely on.                                              |
| `skip-cronjob-deploy`  | Deployment to cron jobs can be skipped. | This is the case if no changes are made that affect cronjobs.                                                                    |
| `skip-daemon-deploy`   | Deployment of daemons can be skipped    | This is the case if you haven't updated daemons or the code they depend on                                                       | 

**If deployment is required:**

- What extra steps are needed to deploy this beyond the standard deploy?
- Do scripts need to be run or things like that?
- If this is more than a quick thing, a new issue should be created in our infra repo: https://github.com/freelawproject/infrastructure/issues/new (if you don’t have access to it, just put the steps here)

---

</details>

**This PR should:**

- [ ] <code>skip-deploy</code>
- [ ] <code>skip-web-deploy</code>
- [ ] <code>skip-celery-deploy</code>
- [ ] <code>skip-cronjob-deploy</code>
- [ ] <code>skip-daemon-deploy</code>

Extra steps to deploy this PR:
1. Run script....


## Screenshots

If this changes the front end, please include desktop and mobile screenshots or videos showing the new feature.

<details>
<summary>Desktop</summary>

YOUR IMAGE(S) HERE

</details>


<details>
<summary>Mobile</summary>

YOUR IMAGE(S) HERE

</details>
