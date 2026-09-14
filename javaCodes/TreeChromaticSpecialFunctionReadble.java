import java.util.*;
import java.math.BigInteger;

public class TreeChromaticSpecialFunctionReadble {

    public static void main(String[] args) {

        Scanner scanner = new Scanner(System.in);

        /*
         * ============================================================
         * Input format:
         *
         * n k
         *
         * Then n-1 edges of the first tree:
         * u1 v1
         * u2 v2
         * ...
         *
         * Then n-1 edges of the second tree:
         * u1 v1
         * u2 v2
         * ...
         *
         * Vertices are numbered from 0 to n-1.
         *
         * Example for n = 4 and k = 3:
         *
         * 4 3
         * 0 1
         * 1 2
         * 1 3
         * 0 2
         * 2 1
         * 2 3
         * ============================================================
         */

        System.out.println("==============================================");
        System.out.println(" Tree Chromatic Special Function");
        System.out.println("==============================================");
        System.out.println();
        System.out.println("Input format:");
        System.out.println("n k");
        System.out.println("Then " + "n-1" + " edges for Tree 1");
        System.out.println("Then " + "n-1" + " edges for Tree 2");
        System.out.println();
        System.out.println("Vertices must be numbered from 0 to n-1.");
        System.out.println();
        System.out.println("Example:");
        System.out.println("4 3");
        System.out.println("0 1");
        System.out.println("1 2");
        System.out.println("1 3");
        System.out.println("0 2");
        System.out.println("2 1");
        System.out.println("2 3");
        System.out.println();
        System.out.println("Enter your input:");
        System.out.println();

        // ------------------------------------------------------------
        // Read the number of vertices and parameter k
        // ------------------------------------------------------------

        int numberOfVertices = scanner.nextInt();
        int numberOfColors = scanner.nextInt();

        // A tree with n vertices always has exactly n-1 edges.
        int numberOfEdges = numberOfVertices - 1;

        // ------------------------------------------------------------
        // Read the edges of the first tree
        // ------------------------------------------------------------

        int[][] firstTreeEdges = new int[numberOfEdges][2];

        for (int edgeIndex = 0; edgeIndex < numberOfEdges; edgeIndex++) {
            firstTreeEdges[edgeIndex][0] = scanner.nextInt();
            firstTreeEdges[edgeIndex][1] = scanner.nextInt();
        }

        // ------------------------------------------------------------
        // Read the edges of the second tree
        // ------------------------------------------------------------

        int[][] secondTreeEdges = new int[numberOfEdges][2];

        for (int edgeIndex = 0; edgeIndex < numberOfEdges; edgeIndex++) {
            secondTreeEdges[edgeIndex][0] = scanner.nextInt();
            secondTreeEdges[edgeIndex][1] = scanner.nextInt();
        }

        // ------------------------------------------------------------
        // Convert the edge lists into adjacency lists.
        // This makes traversing the trees easier.
        // ------------------------------------------------------------

        List<Integer>[] firstTreeAdjacency =
                createAdjacencyList(numberOfVertices);

        List<Integer>[] secondTreeAdjacency =
                createAdjacencyList(numberOfVertices);

        // Add edges of Tree 1
        for (int[] edge : firstTreeEdges) {
            int vertexU = edge[0];
            int vertexV = edge[1];

            firstTreeAdjacency[vertexU].add(vertexV);
            firstTreeAdjacency[vertexV].add(vertexU);
        }

        // Add edges of Tree 2
        for (int[] edge : secondTreeEdges) {
            int vertexU = edge[0];
            int vertexV = edge[1];

            secondTreeAdjacency[vertexU].add(vertexV);
            secondTreeAdjacency[vertexV].add(vertexU);
        }

        // ------------------------------------------------------------
        // Root both trees at vertex 0.
        //
        // The adjacency lists describe undirected trees.
        // We convert them into rooted trees, where every vertex
        // has a list of children.
        // ------------------------------------------------------------

        List<List<Integer>> firstTreeChildren =
                buildRootedTree(firstTreeAdjacency, numberOfVertices);

        List<List<Integer>> secondTreeChildren =
                buildRootedTree(secondTreeAdjacency, numberOfVertices);

        // ------------------------------------------------------------
        // Maximum possible degree of the polynomial.
        // ------------------------------------------------------------

        int maximumDegree = numberOfVertices * numberOfColors;

        // ------------------------------------------------------------
        // Compute the special polynomial for each tree.
        // ------------------------------------------------------------

        BigInteger[] firstTreePolynomial =
                computeTreePolynomial(
                        firstTreeChildren,
                        numberOfVertices,
                        numberOfColors,
                        maximumDegree
                );

        BigInteger[] secondTreePolynomial =
                computeTreePolynomial(
                        secondTreeChildren,
                        numberOfVertices,
                        numberOfColors,
                        maximumDegree
                );

        // ------------------------------------------------------------
        // Print the two polynomials
        // ------------------------------------------------------------

        System.out.println();
        System.out.println("==============================================");
        System.out.println("Tree 1 Polynomial:");
        System.out.println("==============================================");
        printPolynomial(firstTreePolynomial);

        System.out.println();
        System.out.println("==============================================");
        System.out.println("Tree 2 Polynomial:");
        System.out.println("==============================================");
        printPolynomial(secondTreePolynomial);

        // ------------------------------------------------------------
        // Compare the coefficients of the two polynomials.
        // ------------------------------------------------------------

        boolean polynomialsAreEqual = true;

        for (int degree = 0; degree <= maximumDegree; degree++) {

            if (!firstTreePolynomial[degree]
                    .equals(secondTreePolynomial[degree])) {

                polynomialsAreEqual = false;
                break;
            }
        }

        // ------------------------------------------------------------
        // Print the final result
        // ------------------------------------------------------------

        System.out.println();

        if (polynomialsAreEqual) {
            System.out.println(
                    "The special functions are equal."
            );
        } else {
            System.out.println(
                    "The special functions are not equal."
            );
        }

        scanner.close();
    }

    /*
     * Creates an empty adjacency list for a graph with n vertices.
     */
    private static List<Integer>[] createAdjacencyList(int numberOfVertices) {

        List<Integer>[] adjacencyList = new List[numberOfVertices];

        for (int vertex = 0; vertex < numberOfVertices; vertex++) {
            adjacencyList[vertex] = new ArrayList<>();
        }

        return adjacencyList;
    }

    /*
     * ============================================================
     * Build a rooted representation of the tree.
     *
     * The input tree is undirected.
     * We root it at vertex 0 using BFS.
     *
     * children.get(u) contains all children of vertex u.
     * ============================================================
     */
    private static List<List<Integer>> buildRootedTree(
            List<Integer>[] adjacencyList,
            int numberOfVertices) {

        List<List<Integer>> children =
                new ArrayList<>();

        for (int vertex = 0; vertex < numberOfVertices; vertex++) {
            children.add(new ArrayList<>());
        }

        Queue<Integer> queue = new LinkedList<>();

        // parent[v] stores the parent of vertex v.
        int[] parent = new int[numberOfVertices];
        Arrays.fill(parent, -1);

        // Start BFS from root vertex 0.
        queue.add(0);

        while (!queue.isEmpty()) {

            int currentVertex = queue.poll();

            for (int neighbor : adjacencyList[currentVertex]) {

                // Do not go back to the parent.
                if (neighbor == parent[currentVertex]) {
                    continue;
                }

                // Set the parent-child relationship.
                parent[neighbor] = currentVertex;

                children.get(currentVertex).add(neighbor);

                queue.add(neighbor);
            }
        }

        return children;
    }

    /*
     * ============================================================
     * Compute the special polynomial of a rooted tree.
     *
     * dp[vertex][color][degree]
     *
     * represents the number of valid color assignments/subtrees
     * rooted at 'vertex', where:
     *
     *   - vertex has color 'color'
     *   - the resulting contribution has polynomial degree 'degree'
     *
     * BigInteger is used because the coefficients can become
     * extremely large.
     * ============================================================
     */
    private static BigInteger[] computeTreePolynomial(
            List<List<Integer>> children,
            int numberOfVertices,
            int numberOfColors,
            int maximumDegree) {

        /*
         * Dynamic programming table:
         *
         * dp[vertex][color][degree]
         */
        BigInteger[][][] dp =
                new BigInteger[
                        numberOfVertices
                        ][
                        numberOfColors + 1
                        ][
                        maximumDegree + 1
                        ];

        // Initialize all DP entries with zero.
        for (int vertex = 0; vertex < numberOfVertices; vertex++) {

            for (int color = 0; color <= numberOfColors; color++) {

                for (int degree = 0; degree <= maximumDegree; degree++) {

                    dp[vertex][color][degree] =
                            BigInteger.ZERO;
                }
            }
        }

        /*
         * Obtain a DFS order.
         *
         * We process this order in reverse so that children
         * are processed before their parents.
         */
        int[] dfsOrder = getDFSOrder(children, 0);

        for (int orderIndex = dfsOrder.length - 1;
             orderIndex >= 0;
             orderIndex--) {

            int vertex = dfsOrder[orderIndex];

            // --------------------------------------------------------
            // Base case:
            // The vertex is a leaf.
            // --------------------------------------------------------

            if (children.get(vertex).isEmpty()) {

                for (int color = 0;
                     color <= numberOfColors;
                     color++) {

                    if (color <= maximumDegree) {
                        dp[vertex][color][color] =
                                BigInteger.ONE;
                    }
                }

            }

            // --------------------------------------------------------
            // Recursive case:
            // The vertex has one or more children.
            // --------------------------------------------------------

            else {

                for (int currentColor = 0;
                     currentColor <= numberOfColors;
                     currentColor++) {

                    /*
                     * 'subtreePolynomial' accumulates the
                     * contributions of all children.
                     *
                     * Initially, it is the polynomial 1.
                     */
                    BigInteger[] subtreePolynomial =
                            new BigInteger[maximumDegree + 1];

                    Arrays.fill(
                            subtreePolynomial,
                            BigInteger.ZERO
                    );

                    subtreePolynomial[0] =
                            BigInteger.ONE;

                    // ------------------------------------------------
                    // Process each child.
                    // ------------------------------------------------

                    for (int child : children.get(vertex)) {

                        /*
                         * Sum all possible states of the child,
                         * except the state where the child's color
                         * is equal to the current vertex's color.
                         */
                        BigInteger[] childPolynomial =
                                new BigInteger[maximumDegree + 1];

                        Arrays.fill(
                                childPolynomial,
                                BigInteger.ZERO
                        );

                        for (int childColor = 0;
                             childColor <= numberOfColors;
                             childColor++) {

                            // Adjacent vertices cannot have
                            // the same color.
                            if (childColor == currentColor) {
                                continue;
                            }

                            for (int degree = 0;
                                 degree <= maximumDegree;
                                 degree++) {

                                childPolynomial[degree] =
                                        childPolynomial[degree]
                                                .add(
                                                        dp[child]
                                                                [childColor]
                                                                [degree]
                                                );
                            }
                        }

                        /*
                         * Multiply the current accumulated
                         * polynomial by the child's polynomial.
                         *
                         * This is ordinary polynomial convolution.
                         */
                        BigInteger[] newSubtreePolynomial =
                                new BigInteger[maximumDegree + 1];

                        Arrays.fill(
                                newSubtreePolynomial,
                                BigInteger.ZERO
                        );

                        for (int firstDegree = 0;
                             firstDegree <= maximumDegree;
                             firstDegree++) {

                            if (subtreePolynomial[firstDegree]
                                    .equals(BigInteger.ZERO)) {
                                continue;
                            }

                            for (int secondDegree = 0;
                                 secondDegree <= maximumDegree;
                                 secondDegree++) {

                                if (firstDegree + secondDegree
                                        > maximumDegree) {
                                    break;
                                }

                                if (childPolynomial[secondDegree]
                                        .equals(BigInteger.ZERO)) {
                                    continue;
                                }

                                newSubtreePolynomial[
                                        firstDegree + secondDegree
                                        ] =
                                        newSubtreePolynomial[
                                                firstDegree + secondDegree
                                                ].add(
                                                subtreePolynomial[firstDegree]
                                                        .multiply(
                                                                childPolynomial[
                                                                        secondDegree
                                                                        ]
                                                        )
                                        );
                            }
                        }

                        subtreePolynomial =
                                newSubtreePolynomial;
                    }

                    /*
                     * Add the contribution of the current vertex.
                     *
                     * If the vertex has color c, its own contribution
                     * increases the degree by c.
                     */
                    for (int degree = 0;
                         degree <= maximumDegree;
                         degree++) {

                        if (degree + currentColor
                                <= maximumDegree) {

                            dp[vertex]
                                    [currentColor]
                                    [degree + currentColor] =
                                    dp[vertex]
                                            [currentColor]
                                            [degree + currentColor]
                                            .add(
                                                    subtreePolynomial[
                                                            degree
                                                            ]
                                            );
                        }
                    }
                }
            }
        }

        /*
         * At the root, any color is possible.
         *
         * Therefore, sum over all possible colors of the root.
         */
        BigInteger[] totalPolynomial =
                new BigInteger[maximumDegree + 1];

        Arrays.fill(
                totalPolynomial,
                BigInteger.ZERO
        );

        for (int rootColor = 0;
             rootColor <= numberOfColors;
             rootColor++) {

            for (int degree = 0;
                 degree <= maximumDegree;
                 degree++) {

                totalPolynomial[degree] =
                        totalPolynomial[degree].add(
                                dp[0][rootColor][degree]
                        );
            }
        }

        return totalPolynomial;
    }

    /*
     * ============================================================
     * Generate a DFS traversal order.
     *
     * The returned order starts at the root and visits parents
     * before their children.
     *
     * computeTreePolynomial() processes this array in reverse
     * order, so children are processed before parents.
     * ============================================================
     */
    private static int[] getDFSOrder(
            List<List<Integer>> children,
            int root) {

        List<Integer> orderList =
                new ArrayList<>();

        Stack<Integer> stack =
                new Stack<>();

        stack.push(root);

        while (!stack.isEmpty()) {

            int currentVertex = stack.pop();

            orderList.add(currentVertex);

            /*
             * Push children in reverse order so that the DFS
             * traversal preserves their original order.
             */
            for (int childIndex =
                 children.get(currentVertex).size() - 1;
                 childIndex >= 0;
                 childIndex--) {

                stack.push(
                        children.get(currentVertex)
                                .get(childIndex)
                );
            }
        }

        // Convert List<Integer> to int[].
        int[] dfsOrder =
                new int[orderList.size()];

        for (int index = 0;
             index < orderList.size();
             index++) {

            dfsOrder[index] =
                    orderList.get(index);
        }

        return dfsOrder;
    }

    /*
     * ============================================================
     * Print a polynomial in the form:
     *
     * a0 q^0 + a1 q^1 + a2 q^2 + ...
     *
     * Zero coefficients are omitted.
     * ============================================================
     */
    private static void printPolynomial(
            BigInteger[] polynomial) {

        boolean isFirstTerm = true;

        for (int degree = 0;
             degree < polynomial.length;
             degree++) {

            // Skip zero coefficients.
            if (polynomial[degree]
                    .equals(BigInteger.ZERO)) {
                continue;
            }

            if (!isFirstTerm) {
                System.out.print(" + ");
            }

            System.out.print(
                    polynomial[degree]
                            + "q^"
                            + degree
            );

            isFirstTerm = false;
        }

        // If every coefficient was zero.
        if (isFirstTerm) {
            System.out.println("0");
        } else {
            System.out.println();
        }
    }
}