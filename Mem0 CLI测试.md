# Mem0 CLI测试

*   初始化
    
    ```shell
    mem0 init --api-key m0-xxx --user-id <user-id>
    ```
    
    ![QQ_1778126658134.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/meonarbaYbNB8qXx/img/46bb5b24-622a-4421-9711-384cb58af8a5.png)
    
*   添加记忆
    

```shell
mem0 add "add text" --user-id <user-id>
mem0 add --file <file-name> --user-id <user-id>
```

![QQ_1778134423428.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/meonarbaYbNB8qXx/img/77d3b0da-07df-4476-a6d5-a09ecf9c5e6d.png)

*   检索记忆
    

```shell
mem0 search <query> --user-id <user-id> --output <json|text|table>
```

![QQ_1778124663063.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/meonarbaYbNB8qXx/img/bf9087a3-19cd-41dc-aeec-2903012a6ba4.png)

*   列出所有记忆
    

```shell
mem0 list --user-id <user-id> --output <json|text|table>
```

![QQ_1778125151753.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/meonarbaYbNB8qXx/img/6df7c103-5c5d-4c0f-9d2b-1a784afd25e5.png)

*   按ID获取指定记忆
    

```shell
mem0 get <memory_id> --output <json|text|table>
```

![QQ_1778125577144.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/meonarbaYbNB8qXx/img/4eafbd32-3a95-4ff2-84e7-be827172364c.png)

*   更新记忆
    

```shell
# 更新记忆内容
mem0 update <memory_id> "update text"
# or
echo "new text" | mem0 update <memory-id>

# 给记忆添加或修改元数据
mem0 update <memory-id> --metadata <metadata-json-string>
```

![QQ_1778125938622.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/meonarbaYbNB8qXx/img/c977cc60-628b-41f8-a390-9e02119b3507.png)

*   删除记忆
    

```shell
# 预览将要删除的记忆，但不进行实际的删除操作，以删除所有记忆为例
mem0 delete --all --dry-run

# 根据记忆ID进行删除
mem0 delete <memory-id>

# 删除特定用户的所有记忆（无需确认）
mem0 delete --entity --user-id <user_id> --force
```

![QQ_1778126450444.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/meonarbaYbNB8qXx/img/2ca0def5-1872-4fe5-9837-fb5f7b354552.png)

*   Agent模式
    

```shell
# 
mem0 --agent add "Alice prefers dark mode and uses vim keybindings" --user-id cli-test
mem0 --agent search "What are Alice's preferences?" --user-id cli-test
mem0 --agent list --user-id cli-test
```

![QQ_1778126885132.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/meonarbaYbNB8qXx/img/101ef3bb-503a-448e-9ddc-3959b7d4557b.png)