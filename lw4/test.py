from constituent_treelib import ConstituentTree, Language
pipeline = ConstituentTree.create_pipeline(
    Language.English, ConstituentTree.SpacyModelSize.Small
)
tree = ConstituentTree("The blood test showed a high level.", pipeline)
print(tree.tree_)