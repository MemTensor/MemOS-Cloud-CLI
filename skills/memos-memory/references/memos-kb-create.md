# `memos kb create`

Intent map:
- create a new knowledge base -> `memos kb create`
- set up a document collection for retrieval -> `memos kb create`

Use this command when:
- the user wants to create a new knowledge base to organize documents or skills;
- a project needs a dedicated knowledge repository.

Command:

```bash
memos kb create --name "<name>" --format json
```

Common flags:

- `--name` (required): knowledge base name
- `--description`: optional description of the knowledge base
- `--format json`

Example:

```bash
memos kb create --name "Project docs" --description "Technical documentation" --format json
```

Working rules:
- `--name` is required; the command will fail without it;
- the response contains `knowledgebase_id` needed for subsequent file operations;
- store the returned `knowledgebase_id` for use with `add-file`, `list-file`, `get-file`, `delete-file`, and `remove`.
